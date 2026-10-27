# 2026-10-26 执行完成说明（优先于下文原始计划）

任务 02 已完成，当前交付与真实验收见 `server/backend/TASK02-RESULT.md`。下文保留原始设计过程，存在以下已明确裁定的差异：

- 五个图记忆标签统一使用原生 get_memory；可选 event_memory_types 覆盖 EventMemory、Context、InsightMemory，不改旧调用默认。
- knowledgeBaseId 真实匹配知识库元数据，不再一律 400。画像无关联则不命中。
- 画像 createTime 使用 created_at；未知主体不伪造为 user。
- 无项目配置时详情返回 50300，不是原计划中的 50000；固定实例默认项目，无请求可变全局状态。
- 实现模块分为 control、memory_models、memory_upstream、memories；测试集中在 test_control、test_memories，未按原计划拆成多份重复文件。
- 为控制模型费用，真实抽取仅一次；实际两条数据每页一条验证分页，25 条多页与大字段由合成回归覆盖。四个空类型的真实有数据详情覆盖未宣称完成。
- 独立审查发现的极端 UTC 日期溢出已通过 3 个 RED→GREEN 用例修复。

完成门槛：后端 110 passed，上游相关 70 passed；pnpm verify、Ruff、Redocly（0 errors、2 条原有 warnings）、两仓库 diff --check 通过。src/shared/server/mock 基线零变更；主前端 5274 仍为 sample；独立验收前端 5276 可查看真实事实与画像。任务 01 真实 HTTP 回归 8 项通过。未提交、推送或推进任务 03。

---


# Issue 3 任务 02：P0 记忆只读（六标签列表与详情）实施计划

对应设计文档：`docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md` 实施顺序第 2 项。
本计划只覆盖任务 02；任务 03（删除/恢复）及之后任务不在范围内。

## 0. 执行约定

- **TDD**：每个行为先写测试（RED），实现后转 GREEN，记录实际 RED/GREEN 结果到交付文档。
- **不执行任何 git commit / push / PR**（用户明确禁止）。所有改动保留在 `feat/dashboard-backend` 工作区。
- 修改范围：`D:/MemOS/dashboard`（server/backend + openapi.json + 文档）与 `D:/MemOS/upstream`（最小只读补充）。
- **禁改**：dashboard `src/`、`shared/`、`server/mock/`、`.env.local`；上游除只读补充外任何语义（尤其删除/写入/数据模型）。
- 现有未提交改动（任务 01 实现与设计文档）完整保留；禁止 reset/clean/checkout 覆盖。
- 基线：dashboard HEAD = 03e10145a4dd8bc3e50b6e2a50ed788d64111945；upstream HEAD = 8d6e231d7d95ea29b6a2716c9c34837644d3e7f6（已存在的 `universal_api.py` 兼容补丁保留）。
- 工具链：`D:\MemOS\.venv\Scripts\python.exe`（3.11.17）；ruff 用 `D:\MemOS\.venv\Scripts\ruff.exe`（独立二进制）；前端 `pnpm`。
- 上游重启：`D:\MemOS\setup\Start-Upstream.ps1`（uvicorn 8000，`PYTHONPATH=upstream/src`）。后端重启：`Stop-Backend.ps1` + `Start-Backend.ps1`（新 env 需在调用前导出）。

## 1. 已核实事实（实现前研究证据，勿凭记忆改动）

以下均已在当前代码与运行服务上核实（2026-10-26）：

1. 上游路由前缀 `/product`（server_router.py:120）。相关端点：
   - `POST /product/get_memory` → `handle_get_memories`（memory_handler.py:427）：按 `include_memory_view` 返回桶；`page/page_size`（cloud 默认 1/10）；`filter` 经 `normalize_filter`（product_models.py:1579）；**无 status 字段**（硬编码 `LISTED_STATUSES=["activated","resolving","frozen","expired"]`）。
   - `include_memory_view` 非 None 时同步布尔标志（product_models.py:1569-1577）：`"preference"→include_preference`、`"skill"→include_skill_memory`、`"tool_memory"→include_tool_memory`；`"detail_factual"`→text_mem 桶（类型 WorkingMemory/LongTermMemory/UserMemory/OuterMemory）、`"event"`→event_mem 桶（EventMemory）。
   - 响应桶形状：`data["text_mem"] = [{"cube_id", "memories": [node...], "total_nodes": int}]`，pref/skill/tool 同理（skill 行经 `_with_skill_url` 补 `metadata.url`）。
   - `GET /product/get_memory/{memory_id}?mem_cube_id=` → 租户钉死：错租户或不存在 → HTTP 200 + `code=200` + `data=None` + message "Memory with ID ... not found"（handle_get_memory 捕获一切异常，memory_handler.py:186-218）。**上游成功码是 200，不能透传为 Dashboard 的 0。**
   - `POST /product/get_event_memories`：`memory_types`（默认 EventMemory/Context/InsightMemory/DreamDiary）、`status`、`search_query`（→ `filter={"memory": {"like": q}}`）、page/page_size；响应 `data={cube_id, memories, total, page, page_size}`，行是 `_graph_node_json` 投影（id/memory/memoryTruncated/memoryType/status/createdAt/updatedAt/...，**无 owner_type**）。
2. 部署后端是 `Neo4jCommunityGraphDB`（`NEO4J_BACKEND=neo4j-community`，继承 `Neo4jGraphDB`）。其 `_parse_node` **总是**把 Qdrant 里的 1024 维向量挂回 `metadata.embedding`（neo4j_community.py:1186-1193）——所以**列表与详情的上游响应永远带 embedding（实测 len=1024）**，列表体积必须靠 Dashboard 投影控制。
3. `export_graph`（继承）：`total_nodes` 在分页前 COUNT（先筛选-再计数-后分页 ✓）；`ORDER BY n.created_at DESC, n.id DESC`（稳定）；`SKIP/LIMIT` 在 Cypher 内；`status` 为列表时 `n.status IN $list`（**缺失 status 的节点被排除**——Cypher 三值逻辑）；`status=None` → `<> 'deleted'`。
4. 过滤翻译（neo4j.py:1893-1961，实测全部通过 `normalize_filter` 且真实链路工作）：
   - `{"k": v}` 标量 → `n.k = $p`；`{"k": None}` → `n.k IS NULL`
   - `{"k": {"gt/lt/gte/lte": v}}` → 比较；`created_at/updated_at` 用 `datetime(n.k) OP datetime($p)`
   - `{"k": {"like": v}}` → `n.k CONTAINS $p`（**大小写敏感**，与 Mock 的不区分大小写不同——记录为契约差异证据）
   - `{"k": {"in": [..]}}` → `n.k IN $p`（值必须是 list）
   - `{"and": [..]}/{"or": [..]}` 嵌套（or 加括号）
   - community 后端叠加日期归一化（neo4j_community.py:561-656）：裸 `YYYY-MM-DD` 会展开边界（lt→次日 0 点、lte→当日末）；带时区的完整 ISO 原样比较（实测 gte/lte 过滤命中真实节点）。
   - **未知操作符（ne/nin/eq/startswith/endswith）静默不产生条件**——不要使用。
   - `GetMemoryRequest.user_id` 传给 `get_all` 后被 `export_graph` 忽略（land in **kwargs）——externalUserId 筛选必须走 `filter`。
5. 真实节点形状（issue3-project-a，实测）：
   ```
   {"id": "61ca5bdd-...", "memory": "用户有一个名为 MemOS-setup-...",
    "metadata": {"memory_type": "UserMemory", "status": "activated", "owner_type": "user",
                 "owner_id": "issue3-project-a", "user_id": "issue3-project-a",
                 "created_at": "2026-10-25T16:16:00.233452+00:00", "updated_at": "...",
                 "embedding": [1024 floats], "history": [...], "sources": <仅 include_sources=true>,
                 "tags": [...], "key", "confidence", "time_basis": "utc", "session_id", ...}}
   ```
   - `_shape_response`（server_router.py:222-233）默认剥 `metadata.sources` 并把时间归一到契约 UTC。
   - owner 语义（owner.py）：租户内每节点恰一个 owner：`owner_type ∈ {user, agent, group, public}` + `owner_id`；user 视图节点 owner_id==user_id；agent 视图（`MEMOS_AGENT_MEMORY_ENABLED` 默认关）owner_id=agent id 且无 user_id；public 仅 `allow_public=True` 时写入，owner_id=租户。
   - SkillMemory：memory=description，`metadata.name`=技能名、`metadata.url`=技能 URL、`metadata.key`=name（process_skill_memory.py:913-930）。
6. ProfileService（api/profile.py）：实例存 MetadataStore（Neo4j `:CloudEntity` 或 JSON，`build_metadata_store(graph_store)`）；`recall` 需要恰好一个 user_id/agent_id（否则异常被 `_profile_bucket` 吞掉返回空——项目级列表拿不到数据）。行形状：`id=f"{entity_id}_{path}"`、`memory=f"{path}: {value}"`、`memory_type="ProfileMemory"`、`template_id/template_name/profile_category/profile_field/profile_path/status="activated"`。绑定实例 `status=="bound"`；字段值空或 deprecated 跳过。
7. 写入路径（真实链路验证用）：
   - `POST /product/add`：`{user_id, mem_cube_id, session_id, async_mode: "sync", mode: "fine", allow_memory_view: [...], messages: [{role, content}], info: {source_type}}` → `data: [{"memory_id": ...}]`（走 Haiku 抽取，调用量需控制）。允许的 view：detail_factual/preference/profile/event/skill/tool_memory。
   - `POST /product/add_profile_template {user_id, mem_cube_id, name, metadata(树)}` → `POST /product/bind_profile_template {mem_cube_id, bind_list:[{user_id, profile_template_id}]}` → `POST /product/edit_profile {mem_cube_id, user_id, profile_template_id, metadata:{path: value}}`。
   - 既有真实租户：issue3-project-a / issue3-project-b；既有标记记忆 61ca5bdd-65bc-4c5d-9fcc-115e7cea396c（**只读，不删除**）。
8. Dashboard 契约（openapi.json + shared/contract.ts + Memories.tsx 实读）：
   - `POST /api/dashboard/project/memory/list`：请求 `{projectId*, memoryDetailType*, pageNum=1, pageSize=50, knowledgeBaseId, startTime, endTime, externalUserId, subjectType(user|agent|public), memSearchContent}`；响应 data `{memListItemResponseList: [Memory], total, current}`。
   - `POST /api/dashboard/project/memory/detail`：请求 `{memoryId*, memType*}`（六标签值之一；**没有 projectId**）。响应 data = Memory。
   - Memory 必填 `memoryId/memoryContent/createTime`；可选 `subjectType/externalUserId/memoryType/skillName/skillUrl/profileTemplateId/profileInstanceId`。前端六个标签固定取值 text_mem/pref_mem/event_mem/profile_mem/skill_mem/tool_mem；搜索框发 memSearchContent；分页默认 pageSize=10，标签计数用 pageSize=1 的 total；event 标签展示 memoryType 列；skill 标签展示 skillName 列。
   - Mock 参照（server/mock/server.ts:197-224, 555-568）：搜索=内容或 skillName 的不区分大小写子串；排序 createTime desc；current=pageNum；publicMemory 白名单投影。
   - 任务 01 已建错误模式：HTTP 400/404/502/503/504/500 + code 40000/40001/40003/50000/50200/50300/50400，信封 `{code, data, message}`，错误 data=null（BackendErrorEnvelope schema 已在 openapi.json）。
9. 现有后端结构：app.py 工厂 + lifespan 注入 `app.state.upstream`（UpstreamClient 包 httpx.AsyncClient，base_url 来自 Settings，超时 3s 默认）；errors.py 有 ApiError/统一 handler；settings.py 冻结 BaseModel + from_env；tests/ 用 `httpx.MockTransport` + TestClient（见 test_meta.py 的 client_for 模式）。`test_errors.py::test_unimplemented_business_route_does_not_return_fake_success` 当前以 memory/list 为目标——**本任务后需重定向**到仍未实现的路由（如 `/api/dashboard/log/list`），保留其原意。
10. 体积验收样本：`D:/MemOS/.local/fixtures/memories-synthetic-10-large.json`（text_mem[0].memories 10 行，每行 ~51KB：embedding 1024 + history + sources），断言投影后 10 行列表响应 < 200 KB。

## 2. 设计决策

### 2.1 六标签映射表（唯一维护点：`server/backend/memories.py`）

| tab | 上游调用 | 上游 memory_type 集合 | 响应桶 | 备注 |
|---|---|---|---|---|
| text_mem | `POST /product/get_memory` `include_memory_view=["detail_factual"]` | WorkingMemory, LongTermMemory, UserMemory, OuterMemory | `data["text_mem"]` | |
| pref_mem | 同上 `include_memory_view=["preference"]` | PreferenceMemory | `data["pref_mem"]` | 图节点（pref_mem 立方体属性已移除） |
| skill_mem | 同上 `include_memory_view=["skill"]` | SkillMemory | `data["skill_mem"]` | 行带 metadata.name/url |
| tool_mem | 同上 `include_memory_view=["tool_memory"]` | ToolSchemaMemory, ToolTrajectoryMemory | `data["tool_mem"]` | |
| event_mem | `POST /product/get_event_memories` `memory_types=["EventMemory","Context","InsightMemory"]` | EventMemory, Context, InsightMemory | `data["memories"]` | **DreamDiary 不在映射范围**：其状态为 completed/context_only，被 activated 口径排除（上游默认四类型里含它，本阶段显式排除并记录） |
| profile_mem | **新增** `POST /product/list_profile_memories` | （画像字段行，非图节点） | `data["memories"]` | 主体可以是项目内任意 user/agent |

每 tab 的 `page/page_size` 直传上游；**status 一律 `["activated"]`**（text/pref/skill/tool 需要上游新增 status 字段；event 端点已支持）。

详情：非 profile → `GET /product/get_memory/{memory_id}?mem_cube_id=<cube>`；profile → **新增** `POST /product/get_profile_memory`。详情校验返回节点的 memory_type ∈ 请求 memType 的类型集合，不匹配 → 40000。

### 2.2 项目映射与授权边界（最小身份）

- 新模块 `server/backend/control.py`：SQLite（`.data/control.db`，路径可由 `DASHBOARD_DATA_DIR` 覆盖），表 `projects(id TEXT PK, name TEXT NOT NULL, upstream_cube_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)`（UTC ISO）。WAL，短连接（每次操作独立连接，本地毫秒级）。
- 种子来自 env `DASHBOARD_PROJECTS`，格式 `"<projectId>:<cubeId>[;<projectId>:<cubeId>...]"`（Settings 校验格式），启动时幂等导入（INSERT OR IGNORE，name 用 projectId）。**不把客户端传入的 projectId 当租户**：列表先查映射，查不到 → 40001。
- 详情请求无 projectId → 用进程级固定 `DASHBOARD_DEFAULT_PROJECT_ID`（必须存在于映射，否则启动即失败）。**不可变、非请求级**，无跨请求串租户风险；跨项目详情因上游租户钉死而返回 40001（与不存在不可区分，不泄露存在性）。完整账号/会话体系仍属 P1（任务 07），本阶段不宣称生产级身份管理。
- 隔离证明：列表用两个 projectId（a/b）对比；详情用**临时第二后端实例**（临时端口 + `DASHBOARD_DEFAULT_PROJECT_ID=issue3-project-b`）请求 A 租户记忆 → 40001。

### 2.3 状态口径

- 六标签默认且唯一口径 `status=["activated"]`；列表与总数同口径（上游先筛选-再 COUNT-后分页，天然满足）。
- **缺失 status 的节点被排除**（Cypher 三值逻辑）——写入路径总是写 status（默认 activated），历史缺失属异常数据；规则写明并测试。
- resolving/frozen/expired/archived/deleted 均不在默认口径（不偷偷混算）。

### 2.4 筛选（先组合、上游执行，不得静默忽略）

| 请求参数 | 处理 |
|---|---|
| projectId | 查 control.db → mem_cube_id；未知 → 40001 |
| memoryDetailType | 六标签枚举校验 → 上游 view/types |
| pageNum/pageSize | `pageNum ≥ 1`；`1 ≤ pageSize ≤ 100`；非法 → 40000 |
| knowledgeBaseId | **显式 40000**："本阶段不支持 knowledgeBaseId 筛选"（记忆-知识库关联属 P2 任务 11，图节点无 kb 字段；不静默忽略） |
| startTime/endTime | 接受 RFC3339 或裸 `YYYY-MM-DD`（上游 community 归一化会按天展开边界）；组合成 `{"and":[{"created_at":{"gte":S}},{"created_at":{"lte":E}}]}`（单边只放一边）；闭区间；缺 created_at 的节点自然排除 |
| externalUserId | `{"or": [{"user_id": v}, {"owner_id": v}]}`（与投影主体 ID 同口径：user 行两者同值；agent 行匹配 owner_id） |
| subjectType | `{"owner_type": st}`（等值；public 匹配 owner_type=public 节点） |
| memSearchContent | text/pref/skill/tool：`{"or": [{"memory": {"like": q}}, {"name": {"like": q}}]}`（对齐 Mock 的"内容或技能名"；Neo4j CONTAINS **大小写敏感**，与 Mock 差异记录为证据）；event：`search_query`（仅 memory，上游语义）；profile：新端点 search 参数（大小写不敏感子串，服务端实现） |

多条件 → `{"and": [每个条件的结构]}` 传 `filter`。`user_id/agent_id` 请求字段**不用**（user_id 被图层忽略、agent_id 会合并进 filter）。

### 2.5 排序与分页

- 排序交给上游 `ORDER BY n.created_at DESC, n.id DESC`（稳定全序）；不在本地重排（本地只有一页，无法全局排序）。
- `total` = 上游过滤后总数（分页前 COUNT）；`current` = pageNum；空桶返回 `[]`/0，不返回假数据。

### 2.6 字段投影（白名单，集中 `memories.py`）

| 契约字段 | 来源（非 profile） | 来源（profile 行） |
|---|---|---|
| memoryId | node.id | row.id（`{entity_id}_{path}`） |
| memoryContent | node.memory；**列表截断 500 字符 + "…"，详情全文** | row.memory（同截断规则） |
| subjectType | metadata.owner_type（user/agent/public；缺失或 group → "user" 兜底，记录） | row.subject_type（user/agent） |
| externalUserId | owner_type=user → metadata.user_id or owner_id；agent → owner_id or agent_id；public → "" | row.subject_id |
| createTime | metadata.created_at（上游已归一 UTC） | row.updated_at（**实例最后写入时间**；字段级创建时间上游不单独记录，口径写明；筛选同口径） |
| memoryType | metadata.memory_type | "ProfileMemory" |
| skillName | metadata.name（仅存在时） | — |
| skillUrl | metadata.url（仅存在时） | — |
| profileTemplateId | — | row.template_id |
| profileInstanceId | — | row.profile_instance_id（entity_id） |

- **绝不输出**：metadata.embedding、sources、history、info、internal_info 及其他一切字段。
- 列表体积预算：10 行 × (截断正文 + ID + 时间) ≪ 200KB（用 .local/fixtures 大样本单测断言）；详情全文不截断（单行 embedding/sources 已剔除）。
- 不得伪造：缺失的 skillName/skillUrl/profile 字段一律省略（模型 Optional，序列化省 null——与 Mock `publicMemory` 一致）。

### 2.7 错误口径（复用任务 01 机制，不新增业务码）

| 场景 | HTTP | code | 说明 |
|---|---|---|---|
| 参数非法（分页越界、枚举错误、时间格式、knowledgeBaseId、memoryId 模式、类型不匹配） | 400 | 40000 | |
| 未知 projectId / 记忆不存在（含跨租户） | 404 | 40001 | 跨租户与不存在不可区分 |
| 上游 HTTP 非 200 / code≠200 / JSON 损坏 / 形状不符 | 502 | 50200 | 不透传上游 message 细节 |
| 上游连接失败 | 503 | 50300 | **绝不包装成成功空列表** |
| 上游超时 | 504 | 50400 | |
| 内部异常 / 未配置默认项目 | 500 | 50000 | 启动时已验证默认项目存在；运行中映射缺失属内部错误 |
- memoryId 入 URL 前校验 `^[A-Za-z0-9_.-]{1,128}$`（覆盖 UUID 与 profile 行 ID `profile_<hex>_<path>`），不匹配 → 40000。

### 2.8 上游补充范围（最小、只读、向后兼容）

1. `GetMemoryRequest.status: list[str] | None = None`（None → 沿用 LISTED_STATUSES，现行为不变；给值 → 直传 get_all）。`handle_get_memories` 的 `list_of` 改用 `get_mem_req.status or LISTED_STATUSES`。
2. `ProfileService.list_field_rows(user_name, *, subject_type, subject_id, search, start_time, end_time, page, page_size)` 与 `get_field_row(user_name, memory_id)`：
   - list：`_instances(user_name)`（bound）→ 展平字段行（含 row id、主体、template、实例时间戳）→ 主体/搜索（大小写不敏感子串，匹配 `f"{path}: {value}"`）/时间（实例 updated_at，闭区间）过滤 → **先 total 后分页** → 排序 `(updated_at DESC, entity_id ASC, path ASC)`。
   - get：上游解析行 ID（`profile_<32hex>_<path>`，按前两个 `_` 切分；路径可含 `_`）→ 取实例 → **租户必须匹配** → status==bound → 字段存在 → 返回行；任一不满足 → None（路由返回 data=None，语义与 get_memory 的 not-found 一致）。
   - 行形状：`{id, memory, memory_type: "ProfileMemory", template_id, template_name, profile_category, profile_field, profile_path, profile_instance_id, subject_type, subject_id, status: "activated", confidence, created_at, updated_at}`。
3. 两个新路由（server_router.py）：`POST /product/list_profile_memories`（请求：mem_cube_id(必填)、subject_type/subject_id、search、start_time/end_time、page=1、page_size=20；响应 BaseResponse[dict] data={cube_id, memories, total, page, page_size}）与 `POST /product/get_profile_memory`（请求：mem_cube_id、memory_id；响应 data=行或 None）。实现放 cloud 侧（与 get_profile 同层，复用 `get_profile_service()`）。
4. **不做**：画像字段删除/恢复（任务 03）、删除语义、写入算法、数据模型变更。
5. 上游 docs/openapi.json 再生：`python -m memos.cli export_openapi --output docs/openapi.json`（PYTHONPATH=src）。

## 3. 任务分解（TDD）

每步先写测试、跑出 RED（记录输出摘要），再实现转 GREEN（记录）。测试文件命名、用例名按下述执行，不得偷改断言迁就实现。

### Phase A：上游最小只读补充（工作目录 D:\MemOS\upstream）

**A1. status 参数（先测后实现）**
- 新增 `tests/api/test_memory_handler_get_views.py::test_cloud_status_field_overrides_listed_statuses`：`GetMemoryRequest(mem_cube_id="c1", status=["activated"])` → `get_all` 收到 `status=["activated"]`；`status=None` → 收到 LISTED_STATUSES（向后兼容）。
- 新增 `tests/api/test_product_models.py`（追加用例）：`GetMemoryRequest(status=["activated"])` 合法；`status="activated"`（非 list）校验失败。
- 实现：product_models.py 加字段（描述注明"None keeps LISTED_STATUSES"；参考 GetMemoryGraphRequest.status 的写法）；memory_handler.list_of 改一行。
- 运行：`$env:PYTHONPATH="D:\MemOS\upstream\src"; & D:\MemOS\.venv\Scripts\python.exe -m pytest tests/api/test_memory_handler_get_views.py tests/api/test_product_models.py -q`。

**A2. ProfileService 行级读取（先测后实现）**
- 新增 `tests/api/test_profile_memory_rows.py`（服务级，`JsonMetadataStore(tmp_path)` 模式，参考 test_profile.py）：
  - `test_list_rows_covers_all_subjects_without_explicit_user`：两个主体（user u1 + agent a1）各绑一实例 → 不带 subject 参数列出全部行（每实例至少 1 字段）。
  - `test_list_rows_subject_and_search_filters`：subject_type=user 只回 user 行；search 命中 `path: value`（大小写不敏感）。
  - `test_list_rows_time_range_on_updated_at`：edit_profile 改值 → updated_at 变化 → 时间窗过滤按实例 updated_at。
  - `test_list_rows_total_before_pagination_and_stable_order`：≥5 行、page_size=2 → total=全量、页间不重叠、排序 (updated_at desc, entity_id, path)。
  - `test_list_rows_empty_tenant_returns_zero`。
  - `test_get_row_roundtrip_and_tenant_isolation`：行 ID → get_field_row 返回同行；**另一租户请求同 ID → None**；detached 实例 → None；不存在的 path → None；坏 ID 格式 → None。
  - `test_get_row_id_with_underscore_in_path`：路径含 `_`（如 `basic.user_name`）解析正确（切分只取前两段）。
- 实现：profile.py 加 `list_field_rows` / `get_field_row`（+ 私有 `_field_row(instance, path)` 复用 recall 的行构造；recall 重构为调用它，行为不变——现有 test_profile.py 必须全绿作为回归）。
- 运行：`-m pytest tests/api/test_profile.py tests/api/test_profile_memory_rows.py -q`。

**A3. 两个新路由（先测后实现）**
- 新增 `tests/api/test_profile_memory_routes.py`（TestClient + `patch("memos.api.handlers.init_server", ...)` 模式，参考 test_cloud_routes.py / test_contract_api.py；profile service 用 JsonMetadataStore(tmp_path)）：
  - `test_list_profile_memories_envelope_and_pagination`
  - `test_list_profile_memories_requires_cube`（缺 mem_cube_id → code=400）
  - `test_get_profile_memory_found_and_not_found`（data=None + message）
  - `test_get_profile_memory_tenant_isolation`（b 租户请求 a 租户行 → data=None）
- 实现：product_models.py 两个请求/响应模型；server_router.py 两条路由；handler 函数放 profile 相关 cloud handler 处（找到 `handle_profile_query` 所在模块并同风格新增 `handle_list_profile_memories` / `handle_get_profile_memory`，service 经 `get_profile_service()`）。
- 再生上游 docs/openapi.json（export_openapi），diff 确认只增两条路径。
- 运行：`-m pytest tests/api/test_profile_memory_routes.py tests/api/test_cloud_routes.py -q`；`& D:\MemOS\.venv\Scripts\ruff.exe check src/memos/api/product_models.py src/memos/api/routers/server_router.py src/memos/api/profile.py`（上游 ruff 配置若存在则用其规则）。

### Phase B：Dashboard 后端（工作目录 D:\MemOS\dashboard）

**B1. settings + control（先测后实现）**
- 新增 `server/backend/tests/test_control.py`：
  - `test_seed_and_resolve`：`Settings(projects_seed=(("p-a","issue3-project-a"),))` → resolve_cube("p-a") == "issue3-project-a"。
  - `test_seed_is_idempotent`：两次启动种子不重复、不报错。
  - `test_unknown_project_returns_none`。
  - `test_default_project_validated_at_startup`：`default_project_id="missing"` → create_app 启动即抛（ValidationError/ValueError，含清晰 message）；合法则通过。
  - `test_projects_env_format_rejected`：`DASHBOARD_PROJECTS="bad-format"` → Settings 校验失败且错误信息不含其他敏感内容。
- 实现：settings.py 加 `projects_seed`（tuple[tuple[str,str],...]）、`default_project_id`、`data_dir`（validator 解析 `DASHBOARD_PROJECTS`）；新 control.py（见 2.2；`open_store(settings)` / `ControlStore.resolve_cube(project_id)` / 启动校验）。app.py lifespan 里初始化 `app.state.control`。
- 注意：`.data/` 已在 .gitignore（任务 01 已加）。

**B2. upstream client 扩展（先测后实现）**
- 新增 `server/backend/tests/test_memories_upstream.py`（MockTransport 断言**请求形状** + 响应解析）：
  - `test_list_memories_sends_view_status_and_filter`：捕获请求体 → `include_memory_view==["detail_factual"]`、`status==["activated"]`、`page/page_size`、`filter` 精确匹配、`mem_cube_id`。
  - `test_list_memories_parses_bucket_rows_and_total`（用真实节点形状 fixture，含 embedding）。
  - `test_list_memories_rejects_upstream_code_400`（→ ApiError 50200/502）。
  - `test_list_memories_rejects_malformed_bucket`（code=200 但桶缺失/非 list → 50200）。
  - `test_list_event_memories_request_shape_and_parse`。
  - `test_get_memory_maps_null_data_to_none`（code=200 + data=None → None；code=400 → 50200）。
  - `test_get_memory_rejects_invalid_id_pattern`（调用前校验）。
  - `test_profile_endpoints_request_shape_and_parse`（新端点）。
  - `test_upstream_body_size_guard`：流式响应超过上限（常量 32 MiB，可注入小值测试）→ 50200。
- 实现：upstream.py 扩展 `list_memories / list_event_memories / get_memory / list_profile_rows / get_profile_row`（统一：`asyncio.timeout(client.timeout.read)`、`client.stream` + 最大字节数守卫、严格 JSON、code==200 校验、形状校验、ApiError 50200/50300/50400 映射——照抄 health() 的模式）。

**B3. 投影模块（先测后实现）**
- 新增 `server/backend/tests/test_memories_projection.py`（纯单元，无 HTTP）：
  - `test_projection_whitelist_drops_large_fields`：真实形状节点（embedding 1024/history/sources/extra）→ 输出 dict 键集 ⊆ 白名单。
  - `test_projection_field_mapping`：id→memoryId、memory→memoryContent、created_at→createTime、owner 映射。
  - `test_projection_owner_variants`：user/agent/public/缺失。
  - `test_projection_skill_fields_present_only_when_real`。
  - `test_projection_truncates_list_content_only`：列表 500+"…"；详情全文。
  - `test_profile_row_projection`：行 → MemoryItem（含 profileTemplateId/profileInstanceId、subject、createTime=updated_at）。
  - `test_list_response_size_under_200kb`：加载 .local/fixtures/memories-synthetic-10-large.json 的 10 行 → 投影 + envelope 序列化 → `len(json) < 200*1024`。
- 实现：memories.py（TabSpec 表 + build_list_filter + project_node + project_profile_row + LIST_CONTENT_LIMIT=500）。

**B4. 路由 + 模型 + openapi（先测后实现）**
- 新增 `server/backend/tests/test_memories_list.py`（TestClient + MockTransport + 临时 control seed）：
  - 六标签各一条 happy path（断言上游请求形状 + 信封 `memListItemResponseList/total/current` + 白名单投影）。
  - `test_unknown_project_404_40001`。
  - `test_knowledge_base_id_explicit_400`（40000，message 含"knowledgeBaseId"）。
  - `test_pagination_validation`（pageNum=0、pageSize=0/101、memoryDetailType 非法 → 40000）。
  - `test_filters_combined`（search+time+subject+externalUserId → 上游 filter 精确断言）。
  - `test_multipage_disjoint_and_total`（fixture 25 行、pageSize=10：页 1/2/3 id 不重叠、total=25、current 正确）。
  - 上游故障矩阵：500/连接失败/超时/坏 JSON/code=400 → 50200/50300/50400，**绝不 200+空列表**。
  - `test_obsolete_task01_check_retargeted` 不在此文件（见 B5）。
- 新增 `server/backend/tests/test_memories_detail.py`：
  - 非 profile 详情 happy path（投影 + 全文）。
  - `test_detail_same_id_content_matches_upstream`（MockTransport 双份同源数据：Dashboard detail 的 memoryContent == 上游 get_memory/{id} 的 memory）。
  - `test_detail_not_found_or_cross_tenant_40001`（上游 data=None）。
  - `test_detail_type_mismatch_40000`（请求 text_mem，节点 memory_type=EventMemory）。
  - `test_detail_profile_row_path`（新端点）+ 行 ID 带 `_` 的路径。
  - `test_detail_without_default_project_config_500`（未配置 → 50000，message 指明 DASHBOARD_DEFAULT_PROJECT_ID）。
  - `test_detail_invalid_memory_id_pattern_400`。
  - `test_detail_second_project_isolation`（第二实例 Settings default=project-b：A 的记忆 → 40001；B 列表不含 A 的标记）。
  - 上游故障 → 502x。
- 实现：models.py（MemoryDetailType/MemorySubjectTypeL/MemoryListRequest/MemoryDetailRequest/MemoryItem/MemoryListData，strict）；app.py 两条路由（list：resolve→校验→filter→分标签调用→envelope；detail：default project→profile 或 graph 路径→类型校验→envelope；`Cache-Control: no-store`）。
- openapi.json（dashboard）：给两条 memory 路径补 400/404/502/503/504/default 错误响应（BackendErrorEnvelope，照 /api/meta 的任务 01 模式）；pageNum/pageSize 补 minimum/maximum；knowledgeBaseId 描述注明"本阶段显式拒绝（40000），知识库范围属后续任务"；不改 shared/ 与 src/。
- 运行：`& D:\MemOS\.venv\Scripts\python.exe -m pytest server/backend/tests -q`（旧 56 + 新增全绿）。

**B5. 过时测试重定向**
- `test_errors.py::test_unimplemented_business_route_does_not_return_fake_success`：目标从 `/api/dashboard/project/memory/list` 改为 `/api/dashboard/log/list`（日志列表属任务 04，仍未实现）。断言不变（404/40001、无假成功）。语义保留：未实现接口不能假成功。
- 同步改 `D:\MemOS\setup\verify_task01.py` 中 `unimplemented_route_not_fake_success` 探测目标（同为 log/list）并重跑其脚本确认全部通过（该脚本属工作区环境，允许更新；报告覆盖写 .local/task01-runtime-verification.json，保留其历史意义并在 TASK02-RESULT 说明）。

### Phase C：真实链路验证

**C1. 重启上游（加载新代码）**
1. 停：按 .local/processes.json 的 upstream 条目（wrapper pid + 8000 python pid），先核对命令行标记再 Stop-Process（照 Stop-Backend.ps1 的归属校验思路）。
2. 起：`powershell -NoProfile -ExecutionPolicy Bypass -File D:\MemOS\setup\Start-Upstream.ps1`（后台；需 infra Docker 已起——Start-Upstream 自己 `compose up -d`）。
3. 等待 /health healthy；**回归**：GET /product/get_memory/61ca5bdd-...?mem_cube_id=issue3-project-a 仍返回原记忆正文（真实数据未受重启影响）；`POST /product/get_memory` status=["activated"] 仍能列出该记忆。
4. 记录重启证据（旧/新 PID、健康检查、回归结果）。

**C2. 重启 5281 后端（新 env）**
```powershell
$env:DASHBOARD_PROJECTS = "issue3-project-a:issue3-project-a;issue3-project-b:issue3-project-b"
$env:DASHBOARD_DEFAULT_PROJECT_ID = "issue3-project-a"
$env:DASHBOARD_UPSTREAM_TIMEOUT_SECONDS = "10"
powershell -NoProfile -ExecutionPolicy Bypass -File D:\MemOS\setup\Stop-Backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File D:\MemOS\setup\Start-Backend.ps1
```
- 验证 /health 与 /api/meta（live）正常；memory/list 可用。

**C3. setup/verify_task02.py（真实链路证据，报告写 .local/task02-runtime-verification.json）**
脚本结构（照 verify_task01.py：httpx 直连、expect() 记录、临时后端实例模式）：
1. `upstream_health_and_version`。
2. **写入**（带唯一标记 `task02-<uuidhex12>`，控制模型调用量并记录 usage）：
   - 12+ 条 text 记忆：循环 `POST /product/add`（每次一条不同事实、`allow_memory_view=["detail_factual"]`、async sync、`info.source_type="issue3_task02_verification"`），直到上游搜索 total ≥ 12（上限 15 次调用）。
   - 尝试 1 条 pref（`allow_memory_view=["preference"]`）与 1 条 event（`allow_memory_view=["event"]`）标记；**实际产生什么类型就记录什么**（是否生成 PreferenceMemory/EventMemory 以列表实测为准，不宣称）。
   - 画像：`add_profile_template`（模板树含 `basic.display_name/city` + `work.role`，name 带标记）→ `bind_profile_template`（user_id=标记主体）→ `edit_profile`（设 display_name="task02-<marker>"、city="Shanghai"）。租户 issue3-project-a；不删除既有内容。
3. **列表发现**：Dashboard `POST /api/dashboard/project/memory/list`（projectId=issue3-project-a、memoryDetailType=text_mem、memSearchContent=标记、pageSize=10）→ 断言命中 ≥1 → 取 memoryId（多页场景记录 total 与页遍历：pageSize=5 全量翻页，id 两两不重叠、总数一致）。
4. **同 ID 对照**：Dashboard detail（memoryId+memType=text_mem）vs 上游 `GET /product/get_memory/{id}?mem_cube_id=issue3-project-a` → `memoryContent` 逐字节相等；`metadata` 大字段（embedding/sources/history）不出现在 Dashboard 响应。
5. **画像链路**：profile_mem 列表能搜到标记行 → 行 detail（profile 行 ID，路径含 `_` 的用例另设字段 `user_name` 验证）→ 与上游 get_profile_memory 同 ID 同值。
6. **项目隔离**：临时后端实例（ephemeral port + default project = issue3-project-b）：A 的 memoryId → 40001；B 列表不含 A 标记；主实例列表（projectId=b）同断言。
7. **六标签真实覆盖盘点**：对每个 tab 真实列表一次（total 与真实行数记录），标注哪些 tab 有真实数据（text/pref/event/profile 视写入结果）与哪些仅合成覆盖（skill/tool——无 REST 写入路径，诚实记录"仅单测+上游形状 fixture 覆盖"）。
8. **体积**：真实列表（pageSize=10）响应字节数记录（真实数据小；大样本体积断言在单测 B3 已证）。
9. **任务 01 回归**：/api/meta live、health、未实现路由（log/list）404 不假成功、前端 .env.local 哈希前后一致、src/ 与基线 diff 为空。
10. 输出 JSON 报告（含 marker、memory_ids、usage、每检查 passed/failed、耗时）。

### Phase D：质量门与交付

**D1. 质量门（全部真实执行并记录输出摘要）**
1. 后端全量：`& D:\MemOS\.venv\Scripts\python.exe -m pytest server/backend/tests -q`。
2. 上游相关：`-m pytest tests/api/test_memory_handler_get_views.py tests/api/test_product_models.py tests/api/test_profile.py tests/api/test_profile_memory_rows.py tests/api/test_profile_memory_routes.py tests/api/test_cloud_routes.py tests/graph_dbs/test_filter_conditions.py -q`（在 upstream 目录 + PYTHONPATH）。
3. Ruff：dashboard `& D:\MemOS\.venv\Scripts\ruff.exe check server/backend` + `ruff format --check server/backend`（用现有 ruff.toml）；上游按其配置对改动文件 check。
4. `pnpm verify`（typecheck + eslint + prettier check + build）。
5. Redocly：`npx redocly@latest lint openapi.json`（若仓库无配置则用默认规则；记录结果）。
6. `git diff --check`（两个仓库）。
7. 基线核对：`git -C D:\MemOS\dashboard diff 03e10145a4dd8bc3e50b6e2a50ed788d64111945 -- src/ shared/ server/mock/` 输出为空；`.env.local` 哈希与验证前一致；5274 前端仍连 Mock（探测其请求目标或查 .env.local 未变）。
8. 上游 docs/openapi.json 再生后 `git -C D:\MemOS\upstream diff --stat` 仅含预期文件。

**D2. 交付文档**
- `server/backend/TASK02-RESULT.md`（主交付，模板）：
  1. 新增/修改文件清单（Dashboard 与上游分列）。
  2. 实施思路摘要 + 六标签映射表 + 项目映射与权限边界说明。
  3. 状态/筛选/排序/分页/投影口径（引用本计划 2.x 的表，标注已实现）。
  4. 实际测试命令与结果（RED/GREEN 记录、pytest/ruff/pnpm/redocly 输出摘要）。
  5. 唯一标记、测试项目、memory ID、同 ID 对照证据（引用 .local/task02-runtime-verification.json，敏感内容不入库）。
  6. 响应体积测量（真实 + 大样本单测数字）。
  7. 可直接运行的请求示例（curl/PowerShell + 人工验证步骤）。
  8. 已知限制与未实现（knowledgeBaseId 显式拒绝、skill/tool 无真实数据、搜索大小写敏感差异、DreamDiary 排除、画像时间戳口径、无账号体系）。
  9. 结论：仅任务 02 完成，不宣称 Issue #3 全部完成。
- `server/backend/README.md`：任务 02 运行说明（env 三变量、启动、验证脚本）。
- `server/backend/.env.example`：补三个新变量示例。
- `docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md`：仅"当前进度"小节追加任务 02 状态（不改设计正文）。

## 4. 验收对照（用户要求 → 证据位置）

| 用户要求 | 证据 |
|---|---|
| 六标签列表/详情 + 字段映射 | B3/B4 测试 + TASK02-RESULT 映射表 |
| 项目范围/隔离（两项目） | test_memories_detail 隔离用例 + C3.6 真实证据 |
| 筛选分页不静默忽略 | B2/B4 请求形状断言 + C3.3 |
| 先筛选再 total 再分页 | 上游 export_graph COUNT 语义 + test_multipage_disjoint_and_total |
| activated 口径 + 缺失状态规则 | A1 + 2.3 规则文档 + 测试 |
| 白名单投影 + <200KB | test_projection_* + size 用例（fixtures 大样本） |
| 失败行为矩阵 | B2/B4 故障用例（不包装成空列表） |
| 同 ID REST 对照 | C3.4（正文逐字节相等） |
| 任务 01 回归 + 过时测试重定向 | B5 + C3.9 + D1.7 |
| 检查清单（pytest/ruff/pnpm/redocly/git/基线） | D1 全项真实输出 |

## 5. 风险与回退

- 上游重启后行为差异（如 embedding 是否仍随行返回）：C1.3 已含真实数据回归检查；差异如实记录，不影响 Dashboard 投影正确性（白名单不依赖上游是否带大字段）。
- /add 抽取产出不稳定（条数/类型）：C3.2 用实际列表结果记录，脚本按实际断言而非期望值。
- 若 event/pref 标记未生成对应类型：记录为真实覆盖缺口（合成单测覆盖），不伪造。
- 所有改动未提交 git，出问题可直接定位文件回退；上游仅 4 个文件 + docs，dashboard 新增模块独立。
