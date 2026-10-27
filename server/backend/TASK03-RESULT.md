# 任务 03：P0 记忆删除、恢复与一致性验收

本任务交付普通记忆和画像字段软删除、恢复、图向量确认、持久操作回执、失败重试和故障测试。仅推进至任务 03；日志及后续任务未实现。原前端 5274 保持 Mock，真实验收前端仍为 5276，src/shared/server/mock 未修改。

主要代码入口：Dashboard 的 `server/backend/memory_lifecycle.py`、`operation_store.py` 及 `memory_upstream.py`/`app.py` 接入；上游的 `src/memos/api/memory_lifecycle.py`、`memory_lifecycle_routes.py`、`control_lock.py`、`memory_state.py`、`memory_visibility.py`，以及 ProfileService、读取/搜索处理器、server_router 和 server_api 生命周期接入。新增回归集中在两仓库对应的 test_memory_lifecycle，以及上游 test_profile_lifecycle、test_lifecycle_routes、test_lifecycle_visibility；原搜索测试仅补齐新的权威状态读取依赖。

## 实现行为

普通记忆在上游保留 Memory 节点、正文和向量点，删除将 status 改为 deleted，保存 previous_status、deleted_at 和生命周期操作 ID。只允许删除 activated 条目，冻结和其他状态拒绝。恢复从上游 previous_status 恢复为 activated，不接受任意客户端状态覆盖。

上游新增可信控制面接口：

| 路径 | 用途 |
|---|---|
| POST /product/inspect_memory_lifecycle | 按 cube 检查真实类型和状态，包含墓碑；不输出正文/向量 |
| POST /product/transition_memory | 普通记忆受控软删除/恢复 |
| POST /product/transition_profile_memory | 单个画像字段软删除/恢复 |
| POST /product/get_memory_operation | 按 cube、operation_id 查询持久意图结果 |

这些接口沿用上游成功 code=200；pending 时 data.success=false，不能只看 HTTP 或 code 判定完成。它们仅供可信内网控制面使用，不构成新增账号权限体系。

上游先在现有 MetadataStore 中保存 memory_lifecycle 意图，再写图、写向量 payload、分别读回状态。不能依赖原 update_node 的 best-effort 同步：本实现直接限定租户更新图，向量异常不吞掉、不伪装成功。缺少已索引向量点或索引状态不明确时也保持 pending；只有真实明确 vector_sync=not_indexed 且确认点不存在，才允许按未索引记录完成。

Neo4j 使用 CloudEntity 锁记录和唯一约束，在持有数据库事务锁时串行处理同一记忆，进程退出后锁自动释放。文件后备存储采用跨进程文件锁。相反操作先完成前一未完成意图；确认过的旧操作 ID 重放只返回历史结果，不重新执行。启动时和每 5 秒运行补偿，失败持续保留待重试意图，不盲目回滚覆盖后续操作。

普通单条、批量、六视图、事件和图谱读取排除 deleted。搜索在返回前按图库当前状态再次校验，图库不可用时返回错误，不能放行旧向量 payload。旧 `/product/get_all` 的搜索子图也过滤已删除邻居和关联边。Neo4j Community 解析器会移除租户字段，因此控制状态通过带租户条件的原生查询读取，不能用解析后缺失字段推断归属。

画像以实例 ID 与字段路径定位，只改变一个字段状态、保留原 value 和算法设置，不删除整个实例，不写 Qdrant。项目列表、字段详情、普通 get_profile 和 recall 隐藏已删除字段。模板同步、手工编辑、算法抽取均保留墓碑且不覆盖删除前值。所有画像写入共享控制锁，避免整份文档并发覆盖。若实例已解除绑定或字段已经弃用，操作明确拒绝，不强制恢复不再有效的字段。

## Dashboard 接口和回执

| 路径 | 行为 |
|---|---|
| POST /api/dashboard/project/memory/delete | 批量软删除；成功保留 data.deleted |
| POST /api/dashboard/project/memory/restore | 恢复；返回 data.restored |
| GET /api/dashboard/project/memory/operation | 按 projectId、operationId 查询回执；查询成功不等于操作已完成，须检查 data.state |
| POST /api/dashboard/project/memory/retry | 仅重试未确认项，沿用上游幂等 ID |

删除/恢复请求必须包含 projectId、memory_ids、memType，最多 100 个互不重复的 ID。可传 operationId，省略由服务端生成。先校验全部目标的项目、标签和状态，再开始写入；部分失败不撤销已确认项，但整体返回 HTTP 503、code=50301，以及操作 ID、确认数、逐项结果。只有全部确认才 code=0。同一个 operationId 用于不同动作或目标返回 409。

SQLite operation_records 在请求上游前保存计划和稳定的逐项操作 ID。网络超时即使无法判断上游是否已执行，也能在后端重启后用同一 ID 查询/重试，已确认项不会再次执行。确认结果单调合并，不被迟到失败回执覆盖。

写请求若携带 Origin，仅接受本机既有控制台端口；不携带 Origin 的可信本机 CLI 可调用。项目范围继续采用任务 02 的显式配置白名单，authEnabled 仍为 false。当前并非生产多用户授权，不应公开本机服务端口。

## 真实数据与故障证据

只新增一个带唯一标记的事实和一个两字段画像，使用一次真实抽取调用。没有删除 Task01/02 原有记忆，也未删除用户记录。所有本次测试记录最终已恢复。

```text
marker: Task03-1a180ab65165
cube: issue3-project-a
subject: task03-user-be7c92cab3
memoryId: 70693895-6d13-4fd7-b55f-6faf5bc4b7f0
profile field: profile_7c5ae18b4e844e4fbd28927954b5198e_basic.user_name
```

| 场景 | 实测结果 |
|---|---|
| 普通软删除 | Dashboard 详情 404，列表 total=0；普通 REST 单条 data=null、批量为空；真实搜索不返回该 ID |
| 独立双边读回 | 直接查询真实 Neo4j 和 Qdrant，均为 deleted；保留原节点与向量点 |
| 恢复 | 同一 ID 恢复为 activated，正文与删除前逐字一致 |
| 画像 | 删除 basic.user_name 后该字段在普通画像接口不可见，另一字段仍在；经过真实服务重启仍不可见；恢复后原字段值和 ID 不变 |
| 图写入后进程退出 | 独立故障进程在真实图提交后以 47 退出；当时图 deleted、向量 activated；最终状态过滤将旧向量命中降为 0 |
| 重启补偿 | 主上游重启后处理持久意图，状态 confirmed；随后恢复成功 |
| 向量连接故障 | 故障进程向不可达本机端口发出真实 TCP 请求；操作 pending、success=false、retryable=true，图 deleted/向量 activated；没有报告成功 |
| 故障恢复 | 使用正常连接的上游重启后后台重试，attempts=2、双边确认；随后恢复 |
| 旧 ID 重放 | 恢复后重放此前删除 operation_id，返回历史 confirmed 回执；记忆仍 activated，没有再次被删除 |
| HTTP 回执丢失与后端重启 | 真实代理先转发并完成删除，再断开响应连接；Dashboard 返回非零 code 和 pending，持久回执在新后端实例中重试后确认；重复重试，上游 attempts 始终为 1；最后恢复原值 |

上述进程中断与向量故障仅针对独立 Task03 测试 ID。故障期间暂停的是项目自有上游进程；共享 Neo4j、Qdrant、网关、Mock 和前端一直保留。故障连接只影响注入进程，不停止共享 Qdrant。

本机原始证据位于：

- `D:/MemOS/.local/task03-runtime-verification.json`
- `D:/MemOS/.local/task03-fault-outage.json`
- `D:/MemOS/.local/task03-deleted-double-readback.json`（独立双边读取均为 deleted）
- `D:/MemOS/.local/task03-fault-read.json`（最终恢复后独立双边读取均为 activated）
- `D:/MemOS/.local/task03-seed.json`（独立测试 ID）
- `D:/MemOS/dashboard/.data/task03-memory-lifecycle/progress.md`（执行与审查记录）

本机辅助工具 `D:/MemOS/setup/verify_task03.py` 和 `task03_fault_probe.py` 是受控的有副作用验收工具，只处理自己的 Task03 种子；不能用作普通无副作用健康检查。仓库内回归测试不调用真实模型、不依赖这些本机文件。

`D:/MemOS/setup/verify_task03_retry.py` 另外验证真实 HTTP 回执丢失、后端实例重启、SQLite 回执恢复与幂等重试，不触碰主后端配置。

## 自动化测试与基线限制

Dashboard 全量测试结果及最终质量检查见下文最终记录。覆盖正常批量、全量预校验、跨项目/错类型、Origin、参数、部分超时、重启后的回执、同 ID 重试、未确认向量不能成功、画像专用路径。

上游新增生命周期故障、画像生命周期、可见性和路由回归，并更新搜索测试的真实状态查询依赖。覆盖图后中断、意图写入失败、向量不可用/丢失/读回不一致、幂等冲突、相反并发、运行中自动重试、画像更新不复活、租户隔离、已删除邻居及关联边过滤。

全量 `tests/api` 确实执行过，并非全部通过：一次运行是 535 passed、18 failed。为判断是否本次引入，另将未修改的 HEAD 源码导出到隔离目录运行，复现完全相同的 18 个失败 ID（513 passed、18 failed）。其中 13 项涉及当前 checkout 缺失的 deploy/soc/tools 维护脚本，4 项为既有硬删除/技能删除测试，1 项为整套运行时 Prompt Mock 类型问题。未把这些原有问题改为 skip/xfail，也没有将它们宣称为通过。

以这 18 个已逐一比对的基线失败作为明确 deselect 后，包含本任务与其他 API 回归的最终运行是 **537 passed、18 deselected**。日志分别保留为 baseline-api-full.log、upstream-api-tests-final.log、upstream-api-baseline-excluded.log。后续任务仍应单独解决这些基线问题。

独立审查发现一个 P1：旧 get_all 子图可返回已删除邻居。已先复现失败断言，再补权威状态和关联边过滤，7 项可见性回归通过；没有遗留审查阻塞项。

## 请求示例

以下示例会更改本次独立测试数据，删除后请执行恢复。

```powershell
$body = @{ projectId='issue3-project-a'; memType='text_mem'; memory_ids=@('70693895-6d13-4fd7-b55f-6faf5bc4b7f0'); operationId='manual-delete-unique-id' }
Invoke-RestMethod http://127.0.0.1:5281/api/dashboard/project/memory/delete -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json)
Invoke-RestMethod 'http://127.0.0.1:5281/api/dashboard/project/memory/operation?projectId=issue3-project-a&operationId=manual-delete-unique-id'
$body.operationId = 'manual-restore-unique-id'
Invoke-RestMethod http://127.0.0.1:5281/api/dashboard/project/memory/restore -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json)
```

## 实施裁定与代价

1. 保留上游原硬删除接口，新增受控生命周期接口；代价是部署必须同步上游补丁，不能只更新 Dashboard。
2. 用现有 MetadataStore 和数据库/文件控制锁持久化意图，不复制记忆正文或向量；代价是当前生产确认链路依赖部署中的 Neo4j 和 Qdrant，其他 provider 未获得实测认证。
3. 补偿期间普通读取以图状态为准，搜索和旧子图增加权威查询；代价是增加读取开销，图库故障时明确失败，不降级放行陈旧向量。
4. 当前只支持 activated 的删除与恢复；代价是冻结、已弃用或解绑画像明确拒绝，不绕过其生命周期。
5. 回执记录部分成功，重试剩余项，不做盲目全批回滚；代价是调用方必须识别非零 code、operationId 和 pending 状态。
6. 不展开 P1 账号授权，也不修改前端源码增加恢复界面；代价是恢复和重试目前通过 API 操作，主前端继续 Mock。
7. 18 项原有 API 失败经 HEAD 对照证实后保留原样，单列报告；代价是上游全量套件目前仍非全绿，不能把本任务通过等同于全仓库验收通过。

本任务不包含任务 04 日志，不提交、推送或创建 PR。

## 最终检查记录

- Dashboard：`python -m pytest server/backend/tests -q`，**119 passed**。
- 上游 API：包含本任务的最终基线排除运行 **537 passed、18 deselected**。18 项失败已用未修改 HEAD 源码逐一对照复现，原测试没有改成 skip/xfail；全量套件仍存在这些基线失败。
- Dashboard Ruff check/format 与上游本任务 17 个改动文件 Ruff check/format 均通过。
- `pnpm verify`：TypeScript、ESLint、Prettier、生产构建通过；保留原有大 chunk 提示。
- Redocly：0 errors，2 条原有警告（license 缺失、localhost servers）。保留并复用 DeleteResult 组件，未新增未使用组件警告。
- 上游 OpenAPI 已通过实际应用导出；Dashboard 当前定义 60 条路径、63 个 HTTP 操作，包含恢复、重试、操作查询三个补充接口。
- 两仓库 diff --check 通过；src/shared/server/mock 对 Dashboard 基线零变更。
- Task01 的 8 项真实 HTTP 回归和 Task02 真实只读回归均通过；5274 仍为 sample，.env.local 哈希不变。
- 本任务所有真实测试项最终恢复：事实同 ID 同正文，画像两字段同 ID 同值；独立 Neo4j/Qdrant 读回均 activated。未提交、推送或创建 PR。
- 最后一次真实搜索已再次召回恢复后的事实 ID；旧 Task01、Task02 两条原始验证记忆均仍存在。
