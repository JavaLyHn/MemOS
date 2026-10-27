# Issue #3 · Task 14 —— P3 密钥：真实持久化、授权完整下发、网关配置同步与重启生效验证

- 日期：2026-10-26
- 状态：设计定稿，待批准
- 规格出处：《2026-10-26-issue3-dashboard-backend-design.md》P3 段（179–183 行）——「密钥完整授权下发；新增、改名、撤销需要真实持久化和网关配置同步、重启生效验证；沿用本设计的数据源与权限，不改前端」
- 前置事实：任务 07–13 已交付真实登录体系（owner/editor/viewer 项目角色 + platform_admin）、control.db 控制面、网关合并文件能力（task12）、`openapi.json` 中 5 条 keys 路径与 ApiKey/ApiKeyRecords/StringData 契约已预定义

---

## 1. 目标

把密钥页从「Mock 假数据」升级为**真链路**：

1. **新增 / 改名 / 撤销**：密钥真实落库（dashboard 重启后仍在），且同步进网关配置文件。
2. **完整密钥授权下发**：只有高权限（项目 owner，含平台管理员）能看到完整密钥。
3. **重启生效**：新建的密钥在网关重启前不可用（实测 401），重启后真实可用（实测 200）；撤销的密钥重启后真实失效（实测 401 回归）。
4. **不改前端 / 不改 Mock**：冻结前端、server/mock/ 一字不动；契约（openapi.json）只改描述文字，不改形状。

## 2. 已定决策（用户拍板或既有事实）

| # | 决策 | 依据 |
|---|------|------|
| D1 | 密钥身份 = 「这个项目」：签发的 token 落网关 `{"user_id": <项目名>, "cube_id": <项目名>}`，网关调用就落在项目自己的记忆空间，用量/日志归因（audit 行 `tenant` 字段）与既有租户口径一致 | 用户拍板（写法一） |
| D2 | 同步载体 = 网关侧预留给控制台的 `deploy/mcp-gateway/tenants.conf` 文件（upstream .gitignore 已预留「含明文 token，任何情况下都不要提交」）；dashboard 持库为准、启动自愈重写该文件；网关最小改动合成加载（env 老 token + 文件新 token 并存） | 方案 A（用户选定） |
| D3 | 创建效果 = 冻结前端既有文案逐字对齐：`密钥已创建。完整密钥只显示这一次，关闭后无法再查看。` + `已写入网关配置。重启网关后这把密钥才能用。`——即 **create 成功返回 ⟺ 网关配置文件已写入**；写失败必须报真实错误、不得假成功，key 一并回滚 | 前端 ApiKeys.tsx 弹窗 + 注释原话（2026-10-19 实测注释） |
| D4 | 「只显示这一次」的显示效果由冻结前端保证（列表页自行 前7+星·7+后8 遮罩，弹窗直接吃 create 响应的完整密钥 + 复制按钮）；后端**照契约原样**：list/copy 仍下发完整密钥，不再另造遮罩语义（不发明 copy 返回遮罩这种新契约） | 用户确认（2026-10-26） |
| D5 | token 格式与 Mock 逐字一致：`sk-` + 48 位十六进制（`secrets.token_hex(24)`，parity with mock `newSecret`） | mock data.ts:54 |
| D6 | 权限：5 条路由全部 `require_role(项目, minimum="owner")`；platform_admin 经 control.role 隐式 owner；`DASHBOARD_AUTH_ENABLED=false` 的老运维模式 actor=None 天然全 owner | control.py 24–51 行既有语义 |
| D7 | 撤销 = 软撤销：行保留（status 置 revoked），立即从配置文件移除；已撤销 id 再 copy/rename → 40001「密钥不存在」（对齐 Mock 删行语义） | Mock copy 语义 |
| D8 | 改名不触网关配置文件（文件里只有 token→身份，没有名字），测试以「文件字节不变」证明 | 文件格式推论 |
| D9 | 网关 token 冲突（env 与文件出现同一 token）→ 网关拒绝启动并明确报错；不静默任选一边 | 诚实工程 |
| D10 | live 验证必须真打网关：401 → 200 → 401 三段 + 老 token 持续可用 + 一条真实只读记忆检索证明 tenant 归因 | 规格原文「重启生效验证」 |

## 3. 被否掉的备选

- **方案 B（重写 `MEMOS_TENANTS` 环境变量进 gateway.env）**：改的是网关进程外环境，需要额外脚本编排，且 env 体积随 key 增长、极易覆盖手工项——否。
- **方案 C（网关 HTTP 轮询 dashboard）**：网关属上游超窄子集、不该携带控制面逻辑与网络依赖，task12 已按此裁决——否。

## 4. 数据模型（control.db 新表 `api_keys`）

沿用 ControlStore 连接（identity/control 同库已是事实）：

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id            TEXT PRIMARY KEY,      -- "key_" + 32hex（对前端不透明）
  project_id    TEXT NOT NULL,         -- dashboard 项目 id（D1：同时是网关 user_id/cube_id）
  name          TEXT NOT NULL,         -- 密钥名称（rename 的对象）
  token         TEXT NOT NULL,         -- "sk-" + 48hex，唯一；明文保存（见 §9 限制）
  token_hash    TEXT NOT NULL UNIQUE,  -- sha256(token)，查重用
  status        TEXT NOT NULL,         -- "active" / "revoked"
  create_time   TEXT NOT NULL,         -- ISO8601（list 按 desc 排序）
  created_by    TEXT,                  -- 账号 id；auth-off 模式为 NULL
  revoke_time   TEXT,
  revoked_by    TEXT
);
```

- 索引：`(project_id, status, create_time DESC)`。
- list 仅回 `status='active'` 行（撤销行从 UI 消失，但库中留档）。
- response 模型按既有 camelCase 别名模式：`id / keyName / apiKey / createTime`（ApiKey 契约字段不变，D4）。

## 5. 模块与路由（server/backend/keys.py 新模块 + app.py 接线）

### 5.1 路由（全部 owner）

| 路由 | 请求 | 响应 | 关键语义 |
|------|------|------|----------|
| POST `/api/dashboard/keys/list` | `{projectId, pageNum?, pageSize?}` | `Envelope[ApiKeyRecords]`（records 按 createTime desc + total） | apiKey=完整密钥（D4）；仅 active |
| POST `/api/dashboard/keys/create` | `{projectId, keyName}` | `Envelope[ApiKey]`（完整密钥唯一出口之一） | 成功 ⟺ 配置文件已写入（D3）；写失败 → 503「网关配置写入失败」，库回滚 |
| POST `/api/dashboard/keys/revoke/{apiKeyId}` | path id | 成功信封 | 文件先移除、后落库（安全优先序）；已撤销/不存在 → 40001 |
| POST `/api/dashboard/keys/copy` | `{apiKeyId}` | `Envelope[StringData]`（完整密钥） | 仅 owner；契约照旧（D4）；前端不调用此接口 |
| POST `/api/dashboard/keys/rename/{apiKeyId}` | `{keyName}` | `Envelope[ApiKey]` | 纯库操作；文件字节不变（D8，测试证明） |

- **行级规则**：revoke/copy/rename 只带 `apiKeyId`，项目从行反查——未知 id 或已撤销 id → 40001「密钥不存在」；行存在但非该项目 owner → 403（权限语义不因 id 可猜测性放水；本地运维控制台规模下可接受）。
- list 排序 `create_time DESC`，并次键 `id DESC` 保稳定。
- 鉴权样板复用 auth.py：`actor_for(request)` → `control_for(settings).with_actor(actor)` → `store.require_role(project_id, minimum="owner")`；写请求过 SessionMiddleware 的 Origin/CSRF 既有约束（与 members/prompts 完全同款）。
- 审计：`SECRET_VALUE` 正则（`sk-[A-Za-z0-9_-]{20,}`，audit_normalize.py 既有）自动把 create/copy 响应中的密钥在 console/审计载荷里打码；测试断言之。

### 5.2 文件同步（`gateway_keys_file` 配置项）

- `settings.py` 新增：`gateway_keys_file: Path | None = None` ← env `DASHBOARD_GATEWAY_KEYS_FILE`（沿用 `or None` 模式）。未配置 → create 显式 503「未配置网关交付路径，拒绝假成功」。
- 文件格式：一个 JSON 对象 `{"<token>": {"user_id": P, "cube_id": P}, ...}`（网关 parse_tenants 已同时支持 JSON 与紧凑串，选 JSON 无歧义）。
- 写法 = 原子替换：同目录临时文件 + `os.replace`；manifest 写入器**收显式 token 集参数**（由调用方以事务连接提供含未提交行的最后状态），不自行查库——避免跨连接读不到未提交数据。
- 归属声明：`tenants.conf` 是本控制台**单向权威管辖**的文件（启动重写即拭除任何库外条目）。README 明示：手工追加 token 请走 `gateway.env` 的 `MEMOS_TENANTS` 环境变量，不要手编本文件。
- **create 序**：库内 `BEGIN IMMEDIATE` 插行（未提交）→ 以「新行在内」重写文件 → 提交。文件失败 → 回滚 + 50；提交失败 → 回滚 + 自愈重写文件（剔除该 token）+ 500。
- **revoke 序**（安全优先）：以「剔除该 token」重写文件 → 库置 revoked → 提交。提交失败 → 自愈重写（恢复该 token）+ 500。任何时刻网关重启看到的库/文件差异由启动重写收敛。
- **启动自愈**：app lifespan 在 store 装配后，若配置了路径 → 以库中 active 集合整体重写文件（孤儿 token 由这台 dashboard 的库拭除——文件属此 dashboard 管辖，单向权威）。

## 6. 网关侧最小改动（upstream/deploy/mcp-gateway，补丁导出）

对 task12 的合并文件能力再推进一小步。网关为包结构（入口 `memos_gateway.py` 在 `deploy/mcp-gateway/` 根，代码在 `gateway/` 包内）：

| 文件 | 改动 |
|------|------|
| `gateway/config.py` | Settings 增加 `tenants_file`（env `MEMOS_TENANTS_FILE`，默认与入口脚本同目录的 `deploy/mcp-gateway/tenants.conf`；缺省文件不存在 → 一行日志后跳过） |
| `gateway/domain/tenants.py` | TenantRegistry 增加 `merge`：env 与文件注册表合并；同 token 双源自变量冲突 → ValueError 明文报「MEMOS_TENANTS 与 tenants.conf 冲突」（D9） |
| `gateway/app.py` | build_app 装配时读文件并合并；其余零改动 |
| `README.md` | 一段说明：文件语义、重启要求、「冲突会拒绝启动」 |
| 新测试 `test_gateway_tenants_file.py` | 与同目录 test_gateway_contract.py 同款脚本式（python 原生、无 fastmcp 依赖）：文件解析、env+file 合并、冲突拒绝、文件不存在继续、verifier_tokens 双源齐全 |

- 导出补丁：`server/backend/patches/task14-gateway-tenants-file.patch` + SHA256 + `git apply --reverse --check` 取证（task12 惯例）；上游测试文件纳入补丁。
- 老语义不动：`MEMOS_TENANTS` env 单独使用时行为与今天完全一致（回归用同目录既有契约锁证明）。

## 7. 运维脚本（setup/）

- 新增 `setup/Restart-Gateway.ps1`：镜像 Start/Stop-Backend 模式——
  1. 从 `.local/gateway.env` 重建 env（**不打印任何值**）；
  2. 由 `.local/processes.json` 的 gateway 条目拿 pid/端口/工作目录，Stop-Process 后以原命令行（`D:\MemOS\.venv\Scripts\python.exe …memos_gateway.py --host 127.0.0.1 --port 8002`）重启；
  3. 轮询 `/health` 到活，更新 processes.json 新 pid；
  4. **端口安全**：只按 processes.json 记录的 pid 停进程；记录失效而 8002 被未知进程占用 → 明确报错并给出占用 pid，提示人工处置（不盲杀）；
  5. 始终 127.0.0.1 本地网关，绝不碰 18000 的 Linux 参照环境。
- dashboard 侧启动注入：Start-Backend.ps1 增加 `-GatewayKeysFile` 参数（默认 `D:\MemOS\upstream\deploy\mcp-gateway\tenants.conf`），不改 `.env.local`。

## 8. 契约与文档

- `openapi.json`：只改 5 条 keys 路径 + ApiKey 字段描述（写明：完整密钥授权下发仅 owner；创建即写入网关配置、重启后生效；撤销即从配置移除、重启后失效；改名不影响网关配置）。形状零变化 → Redocly 保持 0 错误、不超过既有 5 条警告。
- `docs/superpowers/specs/2026-10-26-issue3-interface-matrix.md`：keys 行由「P3 后续扩展」改为「已实现（task14）」+ 描述要点。
- `server/backend/README.md`：`DASHBOARD_GATEWAY_KEYS_FILE` 用法、重启要求、明文保存的诚实声明。

## 9. 诚实限制（写进 README/RESULT，不粉饰）

1. **明文保存**：token 明文存于 `.data/control.db` 与网关 `tenants.conf`（两者均在 gitignore 范围内）。无 KMS 的本地部署里，任何「加密存储」都是装饰品——选择如实不加密，靠目录权限与 gitignore 兜底；因此「关闭后无法再查看」是**前端显示效果（冻结前端保证）+ 契约字段照旧**，取回通道（list/copy）仍是 owner 权限的完整下发（D4）。
2. **双资源非全局原子**：文件+库两段式各带回滚/自愈，收敛点 = 库为准的启动重写；不做超出 SQLite 事务能力的承诺。
3. **重启生效是设计使然**：网关读配置是一次性的（README 既有语义），弹窗文案如实提示「重启后才能用」。

## 10. 验证清单（TDD + 真链路）

### 10.1 RED→GREEN（dashboard 侧，test_keys.py）
匿名 401 / 非 owner（viewer、editor、他项目 owner）403 / 未配置交付路径 create 503 / create 契约形状与 sk-48hex 唯一性 / list 排序分页 + 仅 active / revoke 软撤销 + 撤销后 copy/rename 40001 / rename 文件字节不变 / 持久化：同一 data_dir 重建 app 实例后行仍在 / 文件同步：create 响应成功前文件已含 token；写失败（只读目录模拟）→ 503 且库无行 / 自愈：启动重写收敛孤儿 token / 审计载荷打码断言。

### 10.2 RED→GREEN（网关侧，test_gateway_tenants_file.py + 既有契约锁）
§6 表列全部。

### 10.3 真链路（live， MUST，证据入 `.data/task14-keys/`）
1. 后端带 `DASHBOARD_GATEWAY_KEYS_FILE` 重启（先验证 keys 空表启动不炸 = 幂等；自愈写 `{}` 空清单为合法文件）。
2. 恶意 Bearer → 网关 401 invalid_token（基线）。
3. 老 env token → 200（合并后持续可用，重启前各验一次）。
4. owner 登录 → HTTP create → 响应含完整 sk-（**不打印进任何日志/证据**）。
5. 立拿新 token 打网关 → 401（复现前端注释的实测语义：重启前不存在）。
6. 确认 tenants.conf 已含该 token（证据= 文件 SHA256 前后变化 + 命中计数，不落地 token 原文）。
7. `setup/Restart-Gateway.ps1` → /health 活。
8. 新 token 打 `/mcp` initialize/tools（stateless）→ 200；并发起一条真实只读记忆检索 → 审计 JSONL（`.local/audit/`）出现 `tenant=<项目>` 行（D1 归因端到端证明）。
9. HTTP revoke → 文件不含该 token（SHA256 再证）→ 重启网关 → 同 token → 401 回归。
10. 老 token 终验 200；传输链全程不打印密钥原文。

**实现期开放项**（写计划时定，不凭记忆假设）：① 读 `gateway/app.py` build_app 的 http transport 实参（是否 stateless_http）来定 MCP 探测载荷形态；② 只读记忆检索的 MCP 工具名以 `tools/list` 实取结果为准，不硬编码。

### 10.4 质量门
dashboard 全量 pytest（≥249 + 新增）、ruff 全绿（58+ 文件）、`pnpm verify`、Redocly 0 错误、保护面 diff 对基线 03e10145 通过、`git diff --check` 干净、补丁逆应用校验通过。

## 11. 留档（用户明示要求：主会话可审）

| 产物 | 位置 |
|------|------|
| 本设计文档 | `docs/superpowers/specs/2026-10-26-issue3-task14-keys-design.md` |
| 实施计划（checkbox 逐项） | `docs/superpowers/plans/2026-10-26-issue3-task14-keys-plan.md` |
| 执行台账（每步 RED/GREEN、命令、结论） | `docs/superpowers/plans/…plan.md` 内嵌 + 进度账 |
| 网关补丁 + SHA + 逆应用证据 | `server/backend/patches/task14-gateway-tenants-file.patch` 等 |
| live 证据 | `.data/task14-keys/` 下 `verification.json` / `task14-live.json`（无密钥原文；token 一律打码或仅存哈希） |
| 验收文档 | `server/backend/TASK14-RESULT.md` |
| 红绿证据 | 各测试文件 + 证据目录内命令输出摘录 |

## 12. builder 自检记录（2026-10-26，禁 subagent 故由设计者冷读代行）

以「从未读过本对话的实施者」身份复读全文，修正 7 处：① 网关路径精确到包内（`gateway/config.py` 等）；② manifest 写入器改为收显式参数，防跨连接读不到事务内未提交行；③ 补 revoke/copy/rename 行级规则（未知/撤销 40001、跨项目 403）；④ 声明 tenants.conf 单向权威、手工 token 走 env；⑤ Restart-Gateway.ps1 加端口占用防误杀；⑥ 证据目录按 `.data/task14-keys/` 惯例定点（核自 `.data/task10-13-p2/`）；⑦ MCP 探测依赖的 transport 配置与工具名列为实现期实证项。

## 13. 后续（本任务之后停下）

任务 14 交付并自验后**停住**，等独立验收；属性树模板（task15/16 相关）不沾。
