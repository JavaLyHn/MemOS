# Task 14 · P3 密钥（持久化 + 授权下发 + 网关配置同步 + 重启生效）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans（本仓执行方式已定：无 subagent、用户本人在场互相校对，逐任务执行）。步骤用 checkbox（`- [ ]`）跟踪。

**Goal:** 把 5 条 `/api/dashboard/keys/*` 路由接到真实控制面：SQLite 持久化 + 网关 `tenants.conf` 合写 + 真实网关重启生效验证（401→200→401）。

**Architecture:** 新增 `key_store.py`（ApiKeyStore + 原子 manifest 写入器，落 control.db 的 `api_keys` 表）与 `keys.py`（5 条路由，全 owner）；dashboard 启动自愈重写 manifest；网关 `deploy/mcp-gateway/` 最小改动合成加载 `tenants.conf`（env 老 token 不动，同 token 冲突拒绝启动），以补丁交付。live 验证用 `setup/Restart-Gateway.ps1`。

**Tech Stack:** FastAPI + pydantic + sqlite3（既有栈）；unittest 脚本（网关侧）；PowerShell（运维脚本）。

**Spec:** `docs/superpowers/specs/2026-10-26-issue3-task14-keys-design.md`

## Global Constraints（每任务隐含）

- 不执行任何 `git commit`/`add`；不碰 `src/`、`shared/`、`server/mock/`、`.env.local`；不碰 18000 的 Linux 参照环境。
- 网关侧所有改动 = 改动 + 导出补丁到 `server/backend/patches/` + SHA256 + `git apply --reverse --check` 取证。
- **任何终端输出、日志、证据 JSON、RESULT 都不得包含完整 token 原文**（`sk-` 开头即打码/换哈希）。
- `openapi.json` 只改描述文字，五条路径形状零变化；Redocly保持 0 错误、≤5 警告。
- pytest 全量保持 ≥249 全绿；ruff 干净；前端契约字段 `id/keyName/apiKey/createTime` 驼峰不变。
- Redis/密钥格式：`sk-` + 48 hex（`secrets.token_hex(24)`）；id = `key_` + 32 hex。

## Review Focus（谁最可能咬人 & 各自钉进哪个任务）

1. **create 半途写文件失败还报成功**（前端注释原话「接口返回成功只代表配置写进去了」）→ Task 2 `test_create_rolls_back_if_manifest_write_fails`（HTTP 503 + 库无行 + 文件不变）。
2. **软撤销后网关重启仍收旧密钥** → Task 1 `active_entries` 排除断言 + Task 7 live 第 9 步（revoke→重启→401）。
3. **已撤销 id 经 copy/rename 再取密钥** → Task 2 `test_revoke_soft_and_aftermath`（revoked → 404，行仍在库）。
4. **非 owner 会话拿到完整密钥** → Task 2 role 矩阵（viewer/editor/跨项目 membership 全 403）。
5. **密钥原文漏进 console 审计 JSONL** → Task 2 `test_console_audit_redacts_token`（读 console JSONL 断言无 `sk-…`）；Task 7 全程不打印。

---

### Task 1: control.db 迁移 + `key_store.py`

**Files:**
- Modify: `server/backend/control.py:87-90 之后`（project_contexts 建表后、种子循环前追加 `api_keys` 建表）
- Create: `server/backend/key_store.py`
- Test: `server/backend/tests/test_keys_store.py`

**Interfaces:**
- Consumes: `ControlStore.connection()`、`Settings(data_dir=…, projects_seed=…, default_project_id=…, auth_enabled=…)`（与 test_accounts.py 相同构造法）；`identity_store.now()`。
- Produces（后续任务按此调用，勿改名）:
  - `ApiKeyStore(control: ControlStore)`，方法一律带 `db: sqlite3.Connection | None = None`，`db=None` 时自开 `connection()`:
    - `insert(db, project_id: str, name: str, created_by: str | None) -> dict`（行 dict，键=表列名；id `key_`+32hex、token `sk-`+48hex 唯一冲突时换 token 重试 3 次）
    - `get(db, key_id: str) -> dict | None`（含 revoked 行）
    - `page(db, project_id: str, page_num: int, page_size: int) -> tuple[list[dict], int]`（仅 active；`ORDER BY create_time DESC, id DESC`）
    - `active_entries(db) -> list[tuple[str, str]]`（token, project_id；仅 active，desc 稳定序）
    - `rename(db, key_id: str, name: str) -> dict | None`（不动 token/status；None=查无）
    - `mark_revoked(db, key_id: str, revoked_by: str | None) -> dict | None`（置 status='revoked'、revoke_time=now()、revoked_by；None=查无）
  - `write_tenants_conf(path: Path, entries: Sequence[tuple[str, str]]) -> None`：原子写入（同目录临时文件 `f"tenants.conf.{os.getpid()}.tmp"` + `os.replace`），内容 `json.dumps({token: {"user_id": u, "cube_id": u}, …}, indent=2) + "\n"`
  - `sync_manifest(store: ApiKeyStore, path: Path) -> None`：`write_tenants_conf(path, store.active_entries())`

- [x] **Step 1: RED 写测试 `tests/test_keys_store.py`**（import `from server.backend.key_store import ApiKeyStore, write_tenants_conf, sync_manifest`；fixture 复用 test_accounts 的 Settings 构造）

```python
CASES = (
    test_create_format_and_listing,        # 3 条密钥：id == "key_"+32hex、token == "sk-"+48hex、token_hash 为 sha256(token)；page(1,2) desc + total=3
    test_rename_keeps_token_and_status,    # rename 后 token/status/create_time 不变、name 变
    test_revoke_soft_row_remains,          # mark_revoked 后：active_entries 不含、get 仍在、revoke_time/revoked_by 落值；重复 revoke → None
    test_persistence_across_control_instances,  # 同一 data_dir 新开 ControlStore 后行仍在、状态保留
    test_write_tenants_conf_shape_and_atomic,   # 值断言: json.loads == {"tok1": {"user_id":"a","cube_id":"a"}}；目录里无 .tmp 残留
    test_sync_manifest_from_store,         # revoke 一把后 sync → 文件只剩 active
)
```

- [x] **Step 2: 跑红** `python -m pytest server/backend/tests/test_keys_store.py -v` → FAIL（ModuleNotFoundError: key_store）
- [x] **Step 3: GREEN 实现** —— control.py 在 project_contexts 建表语句后**原位追加**：

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  token TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  create_time TEXT NOT NULL,
  created_by TEXT,
  revoke_time TEXT,
  revoked_by TEXT
)
```
加 `CREATE INDEX IF NOT EXISTS api_keys_active ON api_keys(project_id, status, create_time DESC, id DESC)`（同一连接同一事务内）。`key_store.py` 按 Interfaces 的签名实现，token 生成 `secrets.token_hex(24)` 加 `"sk-"` 前缀，id `secrets.token_hex(16)` 加 `"key_"` 前缀，`token_hash=hashlib.sha256(token.encode()).hexdigest()`，create_time `now()`。
- [x] **Step 4: 跑绿** `python -m pytest server/backend/tests/test_keys_store.py -v` → 6 PASSED；再 `python -m pytest server/backend/tests -q` 全绿（≥249）
- [x] **Step 5: 台账登记**（计划文件内勾选 + 一行结论写 `.data/task14-keys/ledger.md`，此后每任务同）

### Task 2: `keys.py` 路由 + 设置项 + 审计脱敏证明

**Files:**
- Modify: `server/backend/settings.py`（字段 + from_env）、`server/backend/app.py`（include keys_router + 状态注入）
- Create: `server/backend/keys.py`
- Test: `server/backend/tests/test_keys.py`

**Interfaces:**
- Consumes: `control_for(request)`（auth.py:23，返回已带 actor 的 store）、`store._row(db, project_id)`（未知/不可见 → ApiError 40001/404「项目不存在或未配置访问范围」）、`store.require_role(project_id, minimum, db)`（不足 → 403）、`identity_store.missing()`（code 40001「资源不存在或不可访问」status 404 —— 与 Mock「密钥不存在」同为 40001）、Task 1 的 ApiKeyStore/write_tenants_conf/sync_manifest、`kb_models.Strict`、`models.Envelope`。
- Produces:
  - Settings 新字段 `gateway_keys_file: Path | None = None`（from_env 取 `DASHBOARD_GATEWAY_KEYS_FILE`，`or None`）。
  - 路由（prefix `/api/dashboard/keys`，全 owner）:
    - POST `/list` {projectId, pageNum?, pageSize?}（pageNum∈[1,10000] pageSize∈[1,100] 默认 1/10，Strict）→ `Envelope[{records:[{id,keyName,apiKey,createTime}], total}]`（HTTP 200）
    - POST `/create` {projectId, keyName:1-64} → `Envelope[ApiKey]`（含完整密钥）
    - POST `/revoke/{id}` → `Envelope[data={"ok": True}]`（对齐契约 components/responses/Ok）
    - POST `/copy` {apiKeyId} → `Envelope[str]`（**data 即密钥字符串本身**，对齐契约「`data` 是密钥字符串本身，不是对象」）
    - POST `/rename/{id}` {keyName:1-64} → `Envelope[ApiKey]`
  - 错误语义：未知/不可见项目 → 404（`_row`）；disabled/archived 项目 → 404（missing）；无/低角色 → 403；未知/已撤销 id → 404（missing，code 40001）；未配置 `gateway_keys_file` 的写操作 → ApiError 503「未配置网关交付路径，无法签发密钥」；manifest 写失败 → ApiError 503「网关配置写入失败，密钥未创建/未撤销」（事务回滚）。

- [x] **Step 1: RED 写 `tests/test_keys.py`**（夹具照 test_accounts：`application(tmp_path, gateway_keys_file=tmp/tenants.json, console_dir=tmp/audit)` 辅助 helper；登录用 `login(web)`；成员用 `POST /admin/tenants/a/members {account_id, role}` 后再 `login(web,"member",“member-password-123")`）

```python
CASES = (
    test_create_contract_shape_and_format,   # data 字段四键驼峰；apiKey 全文匹配 ^sk-[0-9a-f]{48}$；两次 create token 不同
    test_list_contract_with_stable_pagination,   # 3 条 → total=3；page(1,2) 按 createTime desc 稳定；apiKey 为完整密钥（契约原样）
    test_copy_returns_raw_string,            # json()["data"] == create 时 apiKey
    test_revoke_soft_and_aftermath,          # revoke → {"ok":True}；list 无此行；copy/rename 均 404；直查 sqlite 行仍在（status='revoked'）
    test_rename_contract_and_manifest_untouched,  # rename 200 → 改名生效；manifest 文件原始字节 == 改名后字节
    test_manifest_written_on_create,         # create 响应 200 后该 token 在 manifest 中且身份 = {"user_id":"a","cube_id":"a"}
    test_role_matrix_forbidden_probes,       # viewer/editor 5 路由全 403；仅 b 项目 membership 的 member 对 a → 404/403（_row 语义）；匿名（未登录另一 client）401
    test_auth_off_mode_owner_pass,           # auth_enabled=False 时未登录 create/list 均 200（actor=None 天然 owner）
    test_create_not_configured_503,          # settings 不给 gateway_keys_file → 5 条写路由 503、list 正常（读不依赖交付）
    test_create_rolls_back_if_manifest_write_fails,  # monkeypatch keys.write_tenants_conf → OSError → 503 + 库 0 行 + list 空
    test_revoke_rolls_back_if_manifest_write_fails,  # 同上：revoke → 503 + 行仍 active + copy 可取
    test_console_audit_redacts_token,        # create 后读 console JSONL（create 的 audit 行），全文不含该 token
    test_self_heal_on_startup,               # (Task 3 落点，本任务先写测试) 同 data_dir 建第二 app → 孤儿 token 被拭除、真 key 保留、空库 → "{}"
)
```

- [x] **Step 2: 跑红** `python -m pytest server/backend/tests/test_keys.py -q` → FAIL（no module keys / 404 route missing）
- [x] **Step 3: GREEN 实现**
  - `settings.py`：`gateway_keys_file: Path | None = None` + from_env 最后一行 `gateway_keys_file=os.environ.get("DASHBOARD_GATEWAY_KEYS_FILE") or None,`
  - `keys.py`：Strict 模型 + `store = ApiKeyStore(control_for(request))`；写序（create/revoke 同构，MANIFEST 写在 `BEGIN IMMEDIATE` 事务内、成功则随事务提交，写失败抛 OSError → 外层 `except OSError: raise ApiError(50301, "网关配置写入失败，密钥未创建/未撤销", status_code=503)`，连接上下文自助回滚）；create 先 `store._row` 校项目（404）再 `require_role(project_id,"owner",db)`（403）再 insert+写文件；revoke/copy/rename 以行反查：`get(key_id)` → None 或 status!='active' → `missing()`；再 `_row(db,row["project_id"])` + `require_role(...,"owner")`；copy 返回 `Envelope(row["token"])`；路由函数不是 async（纯 sqlite 快操作，零上游 IO）→ 用 `def`，响应头照 prompts.py `Cache-Control: no-store`；
  - `app.py`：`app.state.keys = ApiKeyStore(...)` 可不做（路由内每请求现取 control），include `keys_router`。
  - 启动自愈留给 Task 3（app.py 的 lifespan"sync"那两行也属于 Task 3）。
- [x] **Step 4: 跑绿** `python -m pytest server/backend/tests/test_keys.py -v` → 13 PASSED；`python -m pytest server/backend/tests -q` 全绿
- [x] **Step 5: ruff & 台账** `ruff check server/backend` 全绿；登记台账

### Task 3: 启动自愈同步 + Start/Restart-Backend 参数透传

**Files:**
- Modify: `server/backend/app.py`（lifespan 内 store 装配后两行）+ **Restart/Start-Backend.ps1 的参数递交**
- Test: 复用 Task 2 的 `test_self_heal_on_startup`（本任务转绿）

**Interfaces:**
- Consumes: Settings.gateway_keys_file、`sync_manifest`（Task 1）。
- Produces: lifespan 内（`app.state.knowledge` 装配行之后）：
  `settings.gateway_keys_file and sync_manifest(...)` —— best-effort，`except OSError as error: print-行日志（不含密钥）`；不阻断 app 启动（可用性优先，且控制台后续写操作会如实报错）。
  - `Start-Backend.ps1`：param 块加 `[string]$GatewayKeysFile = 'D:/MemOS/upstream/deploy/mcp-gateway/tenants.conf'`；`$env:DASHBOARD_GATEWAY_KEYS_FILE = $GatewayKeysFile`；state['backend'] 加字段；differ 检查加一行（不一致 throw）。
  - `Restart-Backend.ps1`：Start 调用追加 `-GatewayKeysFile $state.gatewayKeysFile`（字段可能不存在于旧 state → `if ($state.PSObject.Properties['gatewayKeysFile'])` 兜底，缺省仍用默认值）。
- [x] **Step 1: 跑 Step 2 已写测试确认红**（test_self_heal_on_startup 当前 FAIL：文件未在启动重写）
- [x] **Step 2: 实现三处**（app.py lifespan / Start-Backend / Restart-Backend）
- [x] **Step 3: 跑绿** `test_keys.py` 全绿 + 全量 suite -q 全绿 + 启动日志断言由测试覆盖
- [x] **Step 4: 台账**

### Task 4: 网关合成加载 + 上游测试锁 + 补丁导出

**Files:**
- Modify: `upstream/deploy/mcp-gateway/gateway/config.py`、`gateway/domain/tenants.py`、`gateway/app.py:42`、`deploy/mcp-gateway/README.md`
- Create: `upstream/deploy/mcp-gateway/test_gateway_tenants_file.py`
- Create: `server/backend/patches/task14-gateway-tenants-file.patch`（导出产物）

**Interfaces:**
- Consumes（既有）: `parse_tenants(raw:str) -> dict[str,Tenant]`（tenants.py:15）、`TenantRegistry(mapping)`、`settings.tenants_raw`；app.py:42 `tenants = TenantRegistry.from_raw(settings.tenants_raw)`。
- Produces:
  - `tenants.py` 新函数：
    - `load_tenants_file(path: str | os.PathLike) -> dict[str, Tenant]`：文件不存在 → `{}` 且返回；读文本 → `parse_tenants(text)`（JSON 对象形态）；JSON 解析失败 → `ValueError(f"tenants file unreadable: {path}")`
    - `merge_tenants(base: dict[str, Tenant], extra: dict[str, Tenant], *, extra_source: str) -> dict[str, Tenant]`：token 冲突 → `ValueError(f"MEMOS_TENANTS 与 {extra_source} 冲突：token {mask_token(tok)}")`；否则 `{**base, **extra}`
  - `config.py`：Settings 增字段 `tenants_file: str`；from_env 里 `tenants_file=os.getenv("MEMOS_TENANTS_FILE") or str(pathlib.Path(__file__).resolve().parent.parent / "tenants.conf")`（import pathlib 顶部加）
  - `app.py:42` 替换为：`tenants = TenantRegistry(merge_tenants(parse_tenants(settings.tenants_raw), load_tenants_file(settings.tenants_file), extra_source="tenants.conf"))`（import 相应）
  - `README.md` 增段（置 MEMOS_TENANTS 段落后）：文件归属控制台、重启生效、冲突拒启、手工 token 走 env 不走文件
- [x] **Step 1: RED 写 `test_gateway_tenants_file.py`**（unittest 脚本风格；`sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))`；只 import `gateway.domain.tenants` 不触 fastmcp；末尾 `unittest.main()`）

```python
CASES = (
    test_load_missing_file_returns_empty,      # 临时目录不存在文件 → {}
    test_load_valid_json_map,                   # {"tok": {"user_id":"a","cube_id":"a"}} → Tenant("a","a")
    test_load_invalid_json_raises,             # 坏 JSON → ValueError
    test_merge_union_and_env_kept,             # env 2 token + file 2 token → 4 全在
    test_merge_collision_raises_with_both_labels,  # 同 token → ValueError 含 "MEMOS_TENANTS" 与 "tenants.conf"
    test_env_alone_unchanged,                   # merge_tenants(parse_tenants(raw), {}) == parse_tenants(raw)
)
```

- [x] **Step 2: 跑红** `python deploy/mcp-gateway/test_gateway_tenants_file.py` → FAIL（ImportError: merge_tenants）
- [x] **Step 3: GREEN 实现 config/tenants/app/README 四处**
- [x] **Step 4: 跑绿** 网关新测试 PASS + 既有契约锁 `python deploy/mcp-gateway/test_gateway_contract.py` 仍 PASS（证明 env 单独使用零回归）
- [x] **Step 5: 补丁导出与取证**（在 `D:\MemOS\upstream`）
  1. `git status --short deploy/` 先看脏区（应只有本任务四文件 + 新测试）
  2. `git add -N deploy/mcp-gateway/test_gateway_tenants_file.py`
  3. `git diff -- deploy/mcp-gateway > D:\MemOS\dashboard\server\backend\patches\task14-gateway-tenants-file.patch`
  4. `git reset -- deploy/mcp-gateway`（解除 intent-to-add；**不 commit**）
  5. `git apply --reverse --check` 该补丁 → exit 0
  6. `git apply --reverse` 该补丁（还原工作区为原样）→ `git status --short deploy/` 应空 → `git apply` 正装回补丁内容 → 工作区回到“改动存在”状态（**全程不 commit**）
  7. `Get-FileHash` patch → SHA256 记入台账
- [x] **Step 6: 台账**（patch 名、SHA、reverse-check exit code）

### Task 5: `setup/Restart-Gateway.ps1`

**Files:**
- Create: `setup/Restart-Gateway.ps1`

**Interfaces:** Consumes `Common.ps1`（$MemosPython/$MemosLocal、`Import-MemosEnv`）、`.local/gateway.env`（KEY=VALUE)、`.local/processes.json` 的 `gateway` 条目（marker="memos_gateway.py", executable=$MemosPython, port）。脚本按 Start/Stop-Backend 既有姿态写，全文如下（照抄即交付）：

```powershell
param([int]$Port = 8002)
. (Join-Path $PSScriptRoot 'Common.ps1')
$statePath = Join-Path $MemosLocal 'processes.json'
if (Test-Path -LiteralPath $statePath) {
    $saved = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
    $entry = $saved.gateway
}
if ($entry) {
    $service = Get-CimInstance Win32_Process -Filter "ProcessId = $($entry.id)" -ErrorAction SilentlyContinue
    if ($service -and $service.ExecutablePath -ne $entry.executable -or ($service -and -not $service.CommandLine.Contains($entry.marker))) {
        throw 'Recorded PID does not belong to this gateway; refusing to stop it'
    }
    if ($service) {
        # 按记录的 pid 杀进程树（镜像 Stop-Backend 的 owned 集合逻辑）
        $owned = @($entry.id); $all = @(Get-CimInstance Win32_Process)
        for ($i = 0; $i -lt $owned.Count; $i++) {
            foreach ($child in @($all | Where-Object { $_.ParentProcessId -eq $owned[$i] })) {
                if ($child.ProcessId -notin $owned) { $owned += $child.ProcessId }
            }
        }
        [array]::Reverse($owned)
        foreach ($id in $owned) { Stop-Process -Id $id -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 500
    }
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    $occupier = (Get-NetTCPConnection -State Listen -LocalPort $Port | Select-Object -First 1).OwningProcess
    throw "Gateway port $Port still occupied by PID $occupier; handle it manually instead of blind-killing"
}
Import-MemosEnv (Join-Path $MemosLocal 'gateway.env')
$hostIp = [Environment]::GetEnvironmentVariable('MEMOS_HOST', 'Process'); if (-not $hostIp) { $hostIp = '127.0.0.1' }
$port = [Environment]::GetEnvironmentVariable('MEMOS_PORT', 'Process'); if ($port) { $Port = [int]$port }
$service = Start-Process -FilePath $MemosPython -ArgumentList @((Join-Path $MemosRoot 'upstream\deploy\mcp-gateway\memos_gateway.py'), '--host', $hostIp, '--port', "$Port") -WorkingDirectory (Join-Path $MemosRoot 'upstream\deploy\mcp-gateway') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $MemosLocal 'logs/gateway.out.log') -RedirectStandardError (Join-Path $MemosLocal 'logs/gateway.err.log') -PassThru
$state = if ($statePath -and (Test-Path -LiteralPath $statePath)) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json } else { [pscustomobject]@{} }
$state | Add-Member -Force -MemberType NoteProperty -Name gateway -Value @{ id = $service.Id; marker = 'memos_gateway.py'; executable = $MemosPython; port = $Port }
$state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
$ready = $false
foreach ($i in 1..30) {
    try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $ready) {
    if (Test-Path -LiteralPath (Join-Path $MemosLocal 'logs/gateway.err.log')) { Get-Content (Join-Path $MemosLocal 'logs/gateway.err.log') -Tail 20 }
    throw "Gateway did not become healthy on port $Port"
}
Write-Host "Gateway restarted on port $Port (PID $($service.Id))"
```

（实现时若发现 gateway 无 `/health` 公共路由，则以 README 记载的探活等价物替换、并在台账注明。）
- [x] **Step 1: 写脚本 + 语法门** `[void][ScriptBlock]::Create((Get-Content -Raw setup/Restart-Gateway.ps1))` exit 0
- [x] **Step 2: offline 断言 checklist**（-WhatIf 不可用；用 `MEMOS_PORT=7999` 副本演练 stop 分支的 pid 校验与端口防误杀 throw —— 台账记录两分支行为）
- [x] **Step 3: 台账**

### Task 6: 契约描述 + interface matrix + README

**Files:**
- Modify: `openapi.json`（5 路由 description + ApiKey.apiKey description，**只动文本**）
- Modify: `docs/superpowers/specs/2026-10-26-issue3-interface-matrix.md`（keys 行改「已实现(task14)」）
- Modify: `server/backend/README.md`（新节「接口密钥（task14）」）

**Produces（描述文字照抄）:**
- list description 追加：「`apiKey` 始终为完整密钥（前端自截断展示）。完整下发仅限项目 owner（平台管理员视同 owner）。点击层级与权限、撤销行不返回。」
- create description：「密钥创建即写入网关配置文件 `DASHBOARD_GATEWAY_KEYS_FILE`（成功返回 ⟺ 已写入），网关须重启方可生效；未配置交付路径或写入失败返回 503，密钥不落库。完整密钥仅创建响应可见一次（前端弹窗），后续 list/copy 仍按契约返回完整密钥（仅 owner）。」
- revoke description：「软撤销：行保留（审计可用），立即从网关配置文件移除，重启网关后失效；撤销成功返回 `{ok:true}`。」
- copy description：「返回完整密钥字符串本身（仅 owner；已撤销/不存在返回 404）。」
- rename description：「仅改名；网关配置文件不含名称，字节不变。」
- ApiKey.apiKey description 追加：「明文保存于本地 control.db 与网关配置文件（gitignore 范围内，无 KMS 不加密——诚实声明）。」
- README 新节：env 用法、重启流程（Restart-Gateway.ps1）、单向权威 & 手工 token 走 env、限制三条（明文/两段式收敛/重启生效）。
- [x] **Step 1: 三文件编辑**（openapi 编辑用精确片段替换，防 JSON 失配）
- [x] **Step 2: 校验** —— Redocly（命令沿用 `.data/task10-13-p2/redocly.log` 所记）0 错误 ≤5 警告；`pnpm verify` 通过；`python -m pytest server/backend/tests -q` 全绿（README/契约不动代码）
- [x] **Step 3: 台账**

### Task 7: live 真链路验收 + 质量门 + RESULT 留档

**Files:**
- Create: `.data/task14-keys/probe_gateway.py`、`.data/task14-keys/task14-live.json`、`.data/task14-keys/verification.json`、`server/backend/TASK14-RESULT.md`

**Step 序（每步有可检查产物）：**
- [x] **Step 1: 预备** —— 读 live 平台管理员凭据（来源：`server/backend/TASK07-RESULT.md` / `.data/task07-09-identity/` 记载；不打印密码）；写 `probe_gateway.py`：`httpx` 探 `/mcp`，Authorization 从环境变量读（**argv 不带 token**），initialize→tools/list（stateless http，Accept: `application/json, text/event-stream`），只输出 `{step, http_status, tool_count}`（工具名以 tools/list 实取为准）；读 `gateway/mcp_api/http.py` 钉 initialize 载荷。
- [x] **Step 2: 后端重启** `setup/Restart-Backend.ps1`（经 Task 3 参数透传带上 `DASHBOARD_GATEWAY_KEYS_FILE`）；`/health` 200、空 keys 启动不炸（自愈写 `{}` 文件存在且合法 JSON）
- [x] **Step 3: 401 基线** 恶意 Bearer → 401 invalid_token
- [x] **Step 4: 老 token 200** 从 `.local/gateway.env` 读老 token（进程内、不打印）→ probe 200
- [x] **Step 5: 登录 create** owner 会话 POST create → 响应含 `sk-…`（响应体不进任何证据文件，token 只在内存传递）
- [x] **Step 6: 新 token 重启前 401** probe → 401（复现前端注释语义）
- [x] **Step 7: 文件证据** tenants.conf SHA256 变化 + `Select-String -Pattern <新token> -SimpleMatch` 命中 1（输出只报「命中数」）
- [x] **Step 8: 重启网关** `setup/Restart-Gateway.ps1` → health 活 + processes.json 新 PID
- [x] **Step 9: 新 token 200 + 真检索** probe 200 + 用 `tools/call` 调 `search_memory`（只读（名称以 tools/list 为准），query 带唯一 marker）→ 审计 JSONL 新行 `tenant` = 项目 id，grep marker 证明写入/读侧一致
- [x] **Step 10: revoke + 重启 + 401 回归** dashboard POST revoke → 文件 SHA 再变 + 命中 0 → Restart-Gateway → probe 401
- [x] **Step 11: 老 token 终验 200**（合并对存量零回归的最终证词）
- [x] **Step 12: 质量门全跑** —— `pytest server/backend/tests -q` 全绿（记录数字）、`ruff check server/backend` 绿、网关两个测试脚本 exit 0、`pnpm verify`、Redocly、保护面 diff vs 03e10145（patch 命令沿用 task12 惯例）、`git diff --check` 干净
- [x] **Step 13: 汇总**写 `verification.json` 无密钥原文（SHA/exit-code/计数）+ `task14-live.json` 十步记录；写 `server/backend/TASK14-RESULT.md`（What/How/如何复验/限制三条/预留后续）；计划 checkbox 全勾；台账结行；**停住**（不触 Task 15/16）

## Self-Review 记录（2026-10-26）

1. **Spec coverage:** 设计文档 §4→T1、§5→T2/T3、§6→T4、§7→T3/T5、§8→T6、§9→T6/T7、§10→T1/T2/T4/T7、§11→全部——无格。
2. **Step scan:** 每步单一可判定产物；ps1 脚本作为「整段照抄」的精确拷贝（skill 容许 exact copy 由规格固定）。
3. **Type consistency:** `write_tenants_conf / sync_manifest / insert / get / page / rename / mark_revoked / active_entries / load_tenants_file / merge_tenants` 在 T1/T2/T3/T4 各引用处拼写一致。
4. **Review Focus:** 五类失败模式全部有归属测试（T2×4、T1+T7×1）。
5. **Proportion:** 计划 ~380 行，主件为签名/测试名/断言与照抄脚本，无程序正文转写。
