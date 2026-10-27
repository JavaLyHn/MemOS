# 时间显示统一格式实施计划（2026-10-26）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans（本仓执行方式已定：无 subagent、内联逐任务 TDD）。步骤用 checkbox（`- [ ]`）跟踪。

**Goal:** 后端对外呈现的时间统一为 `YYYY-MM-DD HH:MM:SS`（固定 UTC+8），存储/机器接口保持 ISO UTC 不变。

**Architecture:** 新增单一转换器 `timefmt.py`；只在 serve/展示边界调用；库存 ISO UTC、JSONL 写入格式、上游过滤条件零改动。

**Tech Stack:** Python stdlib（datetime/timedelta/timezone）；pytest。

**Spec:** `docs/superpowers/specs/2026-10-26-time-display-design.md`（批准方案 A）。

## Global Constraints

- 不 commit / 不 push（用户全局禁令）；工作树改动 + 档案落 `.data/time-display-fix/`。
- 不改 `src/`、`shared/`、`server/mock/`、`.env.local`、前端；openapi 零改动（时间字段本为自由 `type: string`）。
- 存储不变量：凡 DB 列/JSONL `ts`/上游请求条件里的时间保持 ISO UTC，逐字节不动。
- 时区：固定 `timezone(timedelta(hours=8))`，格式 `%Y-%m-%d %H:%M:%S`。
- 测试命令：cwd `D:\MemOS\dashboard`，`$env:DASHBOARD_AUTH_ENABLED='true'; D:\MemOS\.venv\Scripts\python.exe -m pytest server/backend/tests -q`；ruff：`python -m ruff check server/backend`。
- 每任务完成后全量 pytest 必须绿；先红后绿，红与绿都要亲眼看。

## Review Focus

1. **None/空串时间字段**（如未归档的 `archived_at`、未撤销的 `revoked_at`）→ 必须原样 None/""，不炸不转。钉在 Task 1。
2. **带 +0800 等非 UTC 时区的输入**（诚实容错）→ 按其时区转同一显示。钉在 Task 1。
3. **排序正确性**（新旧行混排、会话/邀请过期、审计 ts 元组比较）→ 存储不动的证明=既有排序/比较测试零改动保持绿（每任务全量绿即证）。
4. **审计归并机器比较**（`audit_index` ingest 的字符串比较、SQL `ts<=?` 微秒）→ JSONL 写入不改；Task 5 验证 `test_audit_index.py:156`（ingest detail createTime=ISO）零改动保持绿。
5. **审计分页 startTime/endTime 输入**是机器语义（date/iso → 微秒 SQL）→ 不转换（无新测试，代码不触碰即证）。

---

### Task 1: timefmt 转换器

**Files:**
- Create: `server/backend/timefmt.py`
- Create: `server/backend/tests/test_timefmt.py`

**Interfaces:**
- Produces: `timefmt.display(value: str | None) -> str | None`（ISO/带时区时刻 → `"YYYY-MM-DD HH:MM:SS"`；None/"" 原样返回）；`timefmt.display_epoch(seconds: float | None) -> str | None`（epoch 秒 → 同显示）。

- [x] **Step 1: 写失败测试** `tests/test_timefmt.py`：
  - `display("2026-10-26T15:30:02.075819+00:00") == "2026-10-26 23:30:02"`（用户原样示例）
  - `display("2026-10-26T01:02:03+00:00") == "2026-10-26 09:02:03"`；`display("2026-10-25T23:00:00+00:00") == "2026-10-26 07:00:00"`（跨日）
  - `display("2026-10-26T10:00:00+0800") == "2026-10-26 10:00:00"`（非 UTC 时区诚实转换）
  - `display(None) is None`；`display("") == ""`
  - `display_epoch(0) == "1970-01-01 08:00:00"`；`display_epoch(None) is None`
  - 末位秒舍位断言：`display("2026-10-26T15:30:02.999999+00:00") == "2026-10-26 23:30:02"`
- [x] **Step 2: 跑红** `pytest server/backend/tests/test_timefmt.py -q` → FAIL：`ModuleNotFoundError: No module named 'timefmt'`（或 ImportError）。
- [x] **Step 3: 实现** `timefmt.py` 两函数（约 15 行；`replace("Z","+00:00")` 兼容；naive 输入按 UTC 处置——库内不变量为 aware，此为防御分支，注释言明）。
- [x] **Step 4: 跑绿** 同命令 → 全 PASS。
- [x] **Step 5: 记台账** `.data/time-display-fix/ledger.md` 建 Task 1 节（含 ruff）。

### Task 2: keys 面（create/list/copy 的 createTime）

**Files:**
- Modify: `server/backend/tests/test_keys.py`（create 用例断言处）
- Modify: `server/backend/keys.py:80`

**Interfaces:**
- Consumes: `timefmt.display`（Task 1）。

- [x] **Step 1: 写失败测试**：`test_keys.py` 新增格式钉 `re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", data["createTime"])`（create 响应），既有 `test_keys_store.py` 排序断言**一律不碰**（存储不动证明）。
- [x] **Step 2: 跑红** 该钉 FAIL（现值 ISO）。
- [x] **Step 3: 改** `keys.py:80` `createTime=display(row["create_time"])`（`from .timefmt import display`）。
- [x] **Step 4: 跑绿** test_keys 全文件 + 全量 pytest → 全 PASS（269+1=270 passed 预期）。
- [x] **Step 5: 台账**。

### Task 3: projects / invites / 账号面

**Files:**
- Modify: `server/backend/tests/test_control.py`（或既有 projects 断言文件）、invites 既有测试文件、账号面既有测试文件（实施时以 grep 定位精确文件与断言行）
- Modify: `server/backend/control.py:238` (`createTime`)、`:247` (`archivedAt`)；`server/backend/invites.py:68` (`expiresAt`，用 `display_epoch`)、`:71` (`revokedAt`)；`server/backend/identity_store.py:99-100`（`created_at`/`last_login_at`，`account()` 是纯 serve 映射器）

**Interfaces:**
- Consumes: `timefmt.display` / `timefmt.display_epoch`。

- [x] **Step 1: 写失败测试**：三处正则钉（projects page 的 createTime+archivedAt；invite 行 expiresAt/revokedAt；`/admin/accounts` 或 `/api/auth/me` 的 created_at）。
- [x] **Step 2: 跑红**（三钉皆 FAIL=现值 ISO）。
- [x] **Step 3: 改** 三文件五站点（invites 的 `iso()` 只服务 expiresAt；实现时 grep `\.iso\(` 确认无其他机器消费点）。
- [x] **Step 4: 跑绿** 全量（272 passed 预期）。
- [x] **Step 5: 台账**。

### Task 4: kb / 知识文件 / 记忆面

**Files:**
- Modify: 既有 kb/memories 测试文件的 createTime 断言处（实施时 grep 定位）
- Modify: `server/backend/knowledge.py:51`（映射元组处）、`knowledge_files.py:181`、`memories.py:42`

**Interfaces:**
- Consumes: `timefmt.display`。

- [x] **Step 1: 写失败测试**（三面各一钉）。
- [x] **Step 2: 跑红**。
- [x] **Step 3: 改**（`memories.py:42` 整行替换为 `display()`）。
- [x] **Step 4: 跑绿** 全量（275 passed 预期）。
- [x] **Step 5: 台账**。

### Task 5: 审计 serve + 终验 + 存档

**Files:**
- Modify: `server/backend/tests/test_audit_api.py`（格式钉）
- Modify: `server/backend/audit_index.py`（`page` 返回行与 `detail` 返回 dict 的 createTime 出口）
- Create: `.data/time-display-fix/ledger.md` 补完 + `docs/superpowers/specs/2026-10-26-time-display-design.md` 追加「执行记录」段

**Interfaces:**
- Consumes: `timefmt.display`。
- Note: ingest 侧（line 219 起 detail 构造）与 `ts` 比较/SQL 全部不碰；`test_audit_index.py:156` 的 ingest ISO 钉零改动保持绿。

- [x] **Step 1: 写失败测试**：test_audit_api.py 行级 createTime 正则钉（读该测试现断言后加钉，不破坏既有行为断言）。
- [x] **Step 2: 跑红**。
- [x] **Step 3: 改** page/detail 两出口 `display()`。
- [x] **Step 4: 跑绿** 全量（276 passed 预期）+ `test_audit_index.py` 零改动绿证。
- [x] **Step 5: 终验**：全量 pytest + ruff + Redocly（`pnpm --package=@redocly/cli dlx redocly lint openapi.json`，0 错 ≤5 警）+ `git diff --check`（双仓）+ 保护面 diff（dashboard 仓 `git diff --stat 03e10145 -- src shared server/mock .env.local` 必须为空）。
- [x] **Step 6: 存档**：台账终节（RED/GREEN 每站记录 + Ruling）+ spec 执行记录段 + 计划 checkbox 全勾。**不 commit。**
