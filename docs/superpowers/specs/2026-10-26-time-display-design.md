# 时间显示统一格式（短设计 · 2026-10-26）

用户要求：后端对外呈现的时间从 `2026-10-26T15:30:02.075819+00:00`（ISO UTC）
统一改为 `2026-10-26 21:32:05`（可读、本地时刻）。**不影响正确性**，并**存档**本次修改。

## 意图与 Why

- 后端所有时刻产自 `identity_store.now()` = `datetime.now(timezone.utc).isoformat()`，
  存库后 API 直接透传 ISO UTC 字符串（keys/projects/invites/kb/记忆/审计全部如此）。
- 已确认用户选定方案 **A**（三选一里唯一不动数据落到机器格式的）。
- 展示时区取固定 **UTC+8**（中国无夏令时，无 tzdata 依赖，Windows 环境确定性）。

## 红线（不做的事）

- 库内存储格式**不变**：全部保持 ISO UTC。`ORDER BY created_at`、会话过期、邀请过期、
  `audit_index` 对 `ts` 的字符串元组比较与 SQL 区间，全部原样工作——这是"不影响正确性"的根。
- JSONL 文件里写入的 `ts` **不改**（机器格式；改写会牵动审计归并解析与比较，属方案 B，已否决）。
- 上游（MemOS :8000）接受的过滤条件（start_time/end_time、`memory_models`/`usage_models`）
  是机器接口，**不动**。
- 不 commit；不动 src/shared/server/mock/.env.local/前端。openapi 状态码与形状零变化
  （时间字段 openapi 本就是自由 `type: string`，无需扫动）。

## 落点（新增 `server/backend/timefmt.py` 单一转换器）

```python
ZH = timezone(timedelta(hours=8))
def display(value) -> str | None:   # ISO/UTC → "YYYY-MM-DD HH:MM:SS"(UTC+8)；None/""→原样
def display_epoch(seconds) -> str   # epoch 秒 → 同上（invites 的 iso()）
```

仅在"给人看的位置"调用（库存 ISO → 出口转换）：

| 站点 | 字段 |
|---|---|
| `control.py` project(238/247) | createTime / archivedAt |
| `keys.py` KeyRecord(80) | createTime |
| `invites.py` iso/revokedAt(68/71) | expiresAt / revokedAt |
| `knowledge.py`(51) / `knowledge_files.py`(181) | createTime |
| `memories.py`(42) | createTime |
| 审计 serve 出口（`audit_index.page/detail` 返回的时间字段） | createTime 等展示字段 |
| 账号/成员列表 serve 出口（实现时按实测行数清点） | createTime 等 |

`audit_index` 入库细节里的 `time` 若出现在 serve 出口则同样转换；
**ingest 比较、SQL 条件一律绕开**。

## 测试（TDD：先红后绿）

1. `tests/test_timefmt.py`：转换器单元（用户原样示例
   `2026-10-26T15:30:02.075819+00:00` → `2026-10-26 23:30:02`；+0800 输入；None/""；
   展示格式回归钉）。
2. 路由层格式钉（把既有断言全面改为正则
   `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$`）：keys（create/list）、audit API 行、
   projects page、invite 行——这些钉在改动前**会红**（现在还是 ISO），即 RED 面。
3. 排序不回归：既有 `ORDER BY created_at DESC` 与 test_keys_store 排序断言原样全绿（零改动即证存储未动）。

## 存档

- `.data/time-display-fix/ledger.md`：RED→GREEN 逐站记录 + Ruling。
- 计划文档：`docs/superpowers/plans/2026-10-26-time-display-plan.md`（本次小改，执行步骤精简）。
- 完成后在本 spec 末尾补「执行记录」段（终值数字 + 文件清单）。

## 批准后流向

`superpowers:writing-plans` → 内联执行（无 subagent，任务态同 task14 全局约束）。

---

## 执行记录（2026-10-26 当日完成）

**终值**：全量 pytest **277 passed**（269 基线 + 8 条 timefmt 单测；格式钉皆并入既有用例，测试计数不变）；ruff 全绿；Redocly 0 错 5 警；双仓 `git diff --check` 干净；保护面 vs `03e10145` **空变化**；openapi 零改动；不 commit。

**实装与设计稿的差异（全部经 Ruling 记录）**：

1. invites 投影比计划多转 **createdAt/usedAt**，create 响应的 createdAt 同转——同出口同族字段半新半旧不可接受；`iso()` 死助手与失效 `datetime/timezone` import 一并清除。
2. knowledge.py 投影把 **updateTime** 与 createTime 一并转换（同上理）；映射改三列 `(source, target, convert)` 注入 `display`。
3. `test_audit_index.py:156` 实为 **serve 级**钉（经 `page(index)` 助手走 `index.page()`），计划误判为 ingest 级；按方案 A 该钉翻转至 `"2026-10-26 10:00:01"`（属设计内行为变更，非回归）。
4. 账号面实测：`identity_store.account()` 是唯一出口（admin/accounts、auth 域共用），其 `created_at/last_login_at` 在 mapper 转换；机器消费面（with_actor/会话）核实无时间比较后放行。

**转换器**：`server/backend/timefmt.py`（`display` + `display_epoch`，固定 `timezone(timedelta(hours=8))`，`%Y-%m-%d %H:%M:%S`；`Z` 容错、naive 按 UTC 防御分支、None/"" 原样）。

**接入站点终清单（全部 serve 边界）**：`keys.py`（createTime）、`control.py`（createTime/archivedAt）、`invites.py`（createdAt/expiresAt/usedAt/revokedAt + create 响应）、`identity_store.py account()`（created_at/last_login_at）、`knowledge.py`（createTime/updateTime）、`knowledge_files.py`（createTime）、`memories.py`（createTime）、`audit_index.py` serve 出口（page 行 + detail 体 createTime）。**未触碰**：所有 DB 列、JSONL `ts` 写入、上游过滤/SQL 条件、`memory_models/usage_models` 机器接口。

**测试动作清单**：`test_timefmt.py` 新建（8 钉）；`test_keys.py`（正则钉替换 fromisoformat 弱钉）、`test_projects.py`（迁移用例硬期望 `2026-01-01 08:00:00`，证 UTC 零点 +8）、`test_invites.py`（expiresAt/revokedAt 钉）、`test_accounts.py`（created_at 钉）、`test_memories.py`（全 tab 正则钉）、`test_knowledge.py`（createTime/updateTime 硬期望）、`test_knowledge_files.py`（正则钉）、`test_audit_api.py`（list+detail 硬期望）、`test_audit_index.py:156`（serve 钉翻转）。`test_keys_store.py` 排序断言等**存储面测试零改动全绿** = 正确性证明。

**live 验证**（5281，两代进程均验）：匿名 401 → 管理员登录 303 → accounts 1 行 + projects 10 行（**含改造前写入的库存行**）在 serve 出口全部 19 字符显示格式。重启 helper：`.data/time-display-fix/restart_via_popen.py`（坐实外层 shell 文件重定向仍会因句柄继承挂起；先例 `verify_task06.py run_ps` 同构）。

**档案**：台账 `.data/time-display-fix/ledger.md`（5 任务 RED→GREEN + Ruling 全程）；pytest 各任务日志、`redocly.log`、`restart_via_popen.py`、`live_display_check.py`；计划 `docs/superpowers/plans/2026-10-26-time-display-plan.md`（checkbox 全勾）。
