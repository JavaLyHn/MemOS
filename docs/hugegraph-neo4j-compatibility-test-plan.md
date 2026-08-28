# HugeGraph 替换 Neo4j 兼容性测试计划

## 1. 文档目的

本文档定义 MemOS 在 HugeGraph（HG）上替代 Neo4j 时必须验证的测试范围、测试数据、结果规范化规则和运行方式。

本文档不把“实现了 `BaseGraphDB`”等同于“已经兼容 Neo4j”。需要分别验证：

1. 结构兼容：上层是否可以通过 `BaseGraphDB` 注入 HugeGraph。
2. 行为兼容：相同输入是否得到等价的节点、边、检索和生命周期结果。
3. 数据兼容：Neo4j 导出数据能否经过明确转换后导入 HugeGraph。
4. 运行兼容：Schema、graphspace、SDK 响应、向量索引和错误处理是否在真实服务中闭环。

当前目标是形成事实测试口径和可复用数据，不包含 provider 修复、Neo4j 行为调整、CI gate、baseline/hash 或远端 MR 操作。

### 1.1 NOW：当前真实状态（As-Is）

| 领域 | 当前状态 | 证据或结论 |
| --- | --- | --- |
| 接口接入 | HugeGraph provider 已注册并继承 `BaseGraphDB` | 结构层可以被 MemOS 注入 |
| 本地 mock 行为 | CRUD、边、过滤、向量适配和 GraphRAG wiring 有测试 | 相关测试当前为 `60 passed, 1 warning` |
| 真实 HugeGraph | REST graph/schema 可读；`graphspace=DEFAULT` 健康检查成功 | 只能证明部分运行链路可用 |
| SDK/Gremlin | 返回包装、默认 graphspace 等问题尚未闭合 | B1、B2 会影响真实读取、计数和健康检查 |
| 上层调用 | `center_status`、过滤参数、多关键词全文检索存在不兼容风险 | B3、B4、B5 尚未通过真实 parity |
| 隔离与迁移 | HG 使用 `user_name` 逻辑租户隔离；Neo4j 使用 multi-database；关系模型不同 | B6、B8 需要显式转换和安全边界验证 |
| 向量检索 | 已抽象为 `BaseVectorIndex`，可外挂 Qdrant/Milvus | 向量服务不是 HugeGraph 原生能力，仍需验证同步和过滤 |

因此，NOW 不是“已经平替 Neo4j”，而是“完成 provider 结构接入，并有一组 mock 证据；真实服务兼容性仍未闭环”。

### 1.2 DESTINATION：必须达到的目标状态（To-Be）

DESTINATION 指 MemOS 实际使用到的 `BaseGraphDB` 能力范围内，HugeGraph 可以作为 Neo4j 的可验证替代后端；不要求 HugeGraph 实现 Neo4j 的全部产品能力。

| 领域 | 必须达到的状态 | 如何判定 |
| --- | --- | --- |
| 结构 | 工厂、配置、上层调用都能初始化 HugeGraph | S-001～S-006 通过 |
| CRUD/关系 | 相同节点、边、更新和删除输入得到等价结果 | C-001～C-009 规范化结果一致 |
| 租户/生命周期 | 不能跨租户读取、删除、建边或召回；状态过滤一致 | T-001～T-006 通过或差异被明确记录 |
| 图遍历 | 方向、深度、路径、context chain 与 Neo4j 结果一致 | G-001～G-006 通过 |
| 检索 | metadata、全文和向量检索的结果集合、排序和错误语义明确一致 | R-001～R-010 通过 |
| 外置向量 | Qdrant 与 Milvus 通过同一 `BaseVectorIndex` 契约接入，替换其中一个不改变图数据契约 | R-007～R-009 通过 |
| 迁移 | Neo4j 数据经过字段/关系转换后可导入 HG，并可抽样回读 | M-001～M-006 通过 |
| 运行 | Schema、graphspace、SDK 响应包装和错误均可诊断 | 至少一次真实 HG + Schema + 向量服务验证通过 |

### 1.3 如何判断 NOW 已到达 DESTINATION

其他开发者必须使用同一份 fixture，在 Neo4j 和 HugeGraph 上执行同一组操作，再按第 5 节规则规范化结果。不能只看 provider 能否 import，也不能只看 mock 测试是否通过。

判定顺序如下：

1. 先执行结构和 mock 测试，确认接入没有破坏 MemOS 工厂及上层 wiring。
2. 用 `tests/fixtures/hugegraph_neo4j_compatibility.json` 装载 9 个节点、5 条有效边和 2 个租户；所有正例的 `expected_ids`、`expected_order`、`expected_path` 是确定性预期。
3. 对 Neo4j 和 HugeGraph 分别执行 C/T/G/R/M 用例，输出统一节点、边、向量结果，并比较集合、顺序、分数误差、错误类型和是否发生越权副作用。
4. 单独执行真实服务检查：Schema、graphspace、Gremlin 响应解包、向量集合、维度错误和清理流程。
5. 只有结构、行为、迁移和运行四类证据都满足第 7 节条件，才能把结果标记为“达到 DESTINATION”；否则必须保留为 NOW，并列出失败用例和阻断编号。

本节是人工验收口径，不新增 CI gate、hash 或冻结 contract。

## 2. 当前状态结论

### 2.1 已具备的能力

- `HugeGraphGraphDB` 已注册到 `GraphStoreFactory`。
- `HugeGraphGraphDB` 结构上继承 `BaseGraphDB`，可以被 `GraphMemoryRetriever` 等组件作为图存储类型使用。
- HugeGraph 使用固定的 `Memory` 顶点、`MEMORY_RELATION` 边和 `relation_type` 属性表达 MemOS 数据。
- 向量检索已经抽象为 `BaseVectorIndex`，HugeGraph 可外挂 Qdrant 或 Milvus。
- 已有 mock/unit 覆盖 CRUD、边、过滤、向量索引适配和 GraphRAG wiring。

### 2.2 尚未达到替换条件的问题

以下问题必须在兼容性测试中明确呈现，不能仅依赖 mock 测试通过：

| 编号 | 当前问题 | 影响 |
| --- | --- | --- |
| B1 | `pyhugegraph` 实际返回 `{"data": ..., "meta": ...}`，当前 `_gremlin_exec()` 没有解包 | Gremlin 读取、计数、全文检索和遍历结果可能为空、错误或形状错误 |
| B2 | `graphspace=None` 在本地 HugeGraph 1.7.0 环境下导致 SDK Gremlin alias 绑定失败 | 默认配置无法保证健康检查成功；显式 `graphspace=DEFAULT` 才成功 |
| B3 | 上层 `TreeTextMemory.get_relevant_subgraph()` 传入 `center_status`，HugeGraph `get_subgraph()` 当前不接收 | 完整 TreeTextMemory 子图流程存在参数级不兼容 |
| B4 | HugeGraph 向量检索当前只处理租户、scope、status；部分 `search_filter`、`filter`、`knowledgebase_ids` 参数未实现 | 过滤条件可能被静默忽略，导致召回结果与 Neo4j 不一致 |
| B5 | HugeGraph 全文检索当前只使用 `query_words[0]` | 多关键词检索和排序语义与调用方预期不一致 |
| B6 | Neo4j 支持 multi-database 物理隔离，HugeGraph 当前使用 `user_name` 逻辑隔离 | 不能直接声称租户隔离强度等价 |
| B7 | HugeGraph Schema 需要预先执行脚本，当前 provider 不自动创建 | 部署成功不等于 provider 可直接启动 |
| B8 | Neo4j 与 HugeGraph 的关系存储模型不同 | 不能直接复用 Neo4j 原始存储数据，必须经过导出/转换/导入 |

### 2.3 已验证的本地证据

验证日期：2026-08-28，目标 worktree 为 `/Users/looksaw/MemOS-hugegraph-provider-only`。

- 本机 HugeGraph 1.7.0 容器和 Qdrant 容器正在运行。
- HugeGraph REST graph/schema 接口可读取 `hugegraph` graph、`Memory` 顶点标签和 `MEMORY_RELATION` 边标签。
- 使用 `graphspace=DEFAULT` 初始化 provider 后，`check_health()` 成功。
- 不设置 graphspace 时，SDK Gremlin 请求出现 alias 绑定错误。
- provider 的原始 Gremlin 结果形如 `[{"data": [3810], "meta": {}}]`，当前代码将外层包装当作业务行处理。
- 使用 REST 接口能够读取已有 Memory 顶点，但 provider `get_node()` 返回的节点 ID 为空；`get_memory_count()` 对包装结果执行 `int()` 时抛出 `TypeError`。
- 现有离线兼容性测试：`60 passed, 1 warning`。
- 现有 live 测试在未设置 `MEMOS_RUN_HUGEGRAPH_LIVE=1` 时：`1 skipped, 1 warning`。

因此当前结论是：结构接入已完成，真实服务行为兼容尚未完成。

## 3. 测试数据

确定性 fixture：

`tests/fixtures/hugegraph_neo4j_compatibility.json`

fixture 的顶层 `tenant` 是测试上下文，写入节点时应作为 `user_name` 传给后端；`metadata` 是 MemOS 节点元数据。fixture 中的 `embedding` 只用于测试数据和外置向量索引，不代表 HugeGraph 原生提供向量检索。

### 3.1 数据覆盖

| 数据维度 | 覆盖内容 |
| --- | --- |
| 租户 | `tenant-a`、`tenant-b` |
| scope | `WorkingMemory`、`LongTermMemory`、`UserMemory` |
| status | `activated`、`archived`、`deleted` |
| 关系 | `PARENT`、`FOLLOWS`、`SUPPORTS` |
| 向量 | 3 维确定性向量，包含同向、近似和低相似度样本 |
| metadata | `key`、`tags`、`importance`、时间、`mem_cube_id`、删除字段 |
| 字符边界 | 中文、双引号、单引号、反斜杠、换行 |
| 隔离边界 | 跨租户读取、删除、建边和向量检索 |
| 不存在数据 | 缺失节点、缺失边、空查询、空 fixture 集合 |

### 3.2 可直接核对的确定性预期

fixture 不是只有输入数据，也包含每个查询的预期结果。其他开发者可以先不连接数据库，检查以下固定事实；连接数据库后再用同样的字段核对 provider 输出：

| fixture 路径或用例 | 预期结果 |
| --- | --- |
| `nodes` | 9 个节点，`tenant-a` 6 个、`tenant-b` 3 个 |
| `edges` | 5 条有效边；每条边的两个端点和边的 `tenant` 相同 |
| `metadata_queries.exact_key` | 只返回节点 `...0001` |
| `metadata_queries.key_in` | 返回 `...0001`、`...0002` |
| `metadata_queries.tag_overlap` | 只返回 `...0002` |
| `metadata_queries.importance_range` | 返回 `...0001`、`...0002` |
| `fulltext_queries.multiple_words` | 返回 `...0002`；同时必须记录实现采用 AND、OR 还是独立排序 |
| `vector_queries.tenant_a_long_term_activated` | 顺序为 `...0001`、`...0002`、`...0003` |
| `vector_queries.tenant_b_isolation` | 只允许 `...0011`，不能出现 tenant-a 的 `...0001`、`...0002` |
| `graph_queries.bounded_path` | 路径为 `...0001 → ...0002 → ...0006` |
| `negative_cases.cross_tenant_edge` | 拒绝建边，且写操作前后数据不变 |
| `negative_cases.tenant_b_reads_tenant_a` | 未找到，且不返回 tenant-a metadata |

ID 表中的 `...0001` 等表示 fixture 中完整 UUID 的末三位，实际比较必须使用完整 ID。完整字段、过滤表达式和所有负例均以 JSON fixture 为准。

### 3.3 数据使用规则

- 不允许把 fixture 中的节点直接写入共享开发 graph，除非测试显式使用隔离 tenant 并保证清理。
- live 测试必须使用独立 graph 或随机化 tenant/ID；fixture 本身不包含秘密和真实用户数据。
- 比较 Neo4j 与 HugeGraph 时，必须先转换为统一节点/边结构，不比较数据库内部 ID、响应包装或属性存储方式。
- `deleted` 节点默认不参与普通导出和激活态召回，但生命周期测试必须单独验证其可见性规则。

## 4. 兼容性测试矩阵

### 4.1 结构与初始化

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| S-001 | mock | `issubclass(HugeGraphGraphDB, BaseGraphDB)` | 成立，且类没有未实现的抽象方法 |
| S-002 | mock | `GraphStoreFactory.from_config()` 使用 `backend=hugegraph` | 返回 `HugeGraphGraphDB` |
| S-003 | live | 使用已存在 graph 和正确 graphspace 初始化并健康检查 | provider 能执行只读健康查询 |
| S-004 | live | graphspace 为空、错误或正确三种配置 | 结果明确可诊断，不允许静默降级为错误 alias |
| S-005 | live | 读取 `Memory` 顶点标签、`MEMORY_RELATION` 边标签及必需属性 | Schema 与 `docker/hugegraph-schema.groovy` 一致 |
| S-006 | live | 不执行 Schema 初始化直接启动 | 错误必须清晰说明前置 Schema 缺失；不能误报为网络故障 |

### 4.2 节点和边 CRUD

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| C-001 | parity | 插入 `tenant-a` 的普通节点并读取 | `id`、`memory`、`metadata` 与规范化结果一致 |
| C-002 | parity | 相同 ID 重复插入 | 结果与 Neo4j 的 upsert/merge 语义明确一致，不产生重复节点 |
| C-003 | parity | 批量插入所有 fixture 节点 | 成功数量、失败输入和向量同步结果可统计 |
| C-004 | parity | 更新 memory、metadata、status 和 embedding | 图数据及向量 payload 同步更新 |
| C-005 | parity | 删除节点 | 节点、关联边和外置向量记录按约定删除 |
| C-006 | parity | 添加已存在端点的 PARENT/FOLLOWS/SUPPORTS 边 | 关系类型和方向可查询 |
| C-007 | parity | 添加缺失端点或跨租户边 | 不得建立越权边；行为必须与文档约定一致 |
| C-008 | parity | 重复添加相同边 | 幂等性与 Neo4j 预期一致，需记录是否允许重复关系 |
| C-009 | parity | 删除指定关系和检查 `edge_exists` | 只影响目标租户、目标端点和目标关系类型 |

### 4.3 租户与生命周期

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| T-001 | parity | `tenant-a` 读取 `tenant-b` 节点 | 返回空或未找到，不暴露节点字段 |
| T-002 | parity | `tenant-b` 删除 `tenant-a` 节点 | 不删除、不改变对方节点 |
| T-003 | parity | 两租户使用相同 query vector 检索 | 结果集合不能交叉 |
| T-004 | parity | activated/archived/deleted 分别读取和检索 | status 过滤语义明确且一致 |
| T-005 | parity | 软删除、恢复和向量状态同步 | 图节点状态和向量 payload 状态一致 |
| T-006 | design | 对比 Neo4j `use_multi_db=True` 与 HG `user_name` 隔离 | 文档必须标注这是隔离模型差异，不得判定为完全等价 |

### 4.4 图遍历

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| G-001 | parity | 按关系类型和 `in/out/both` 获取邻居 | 节点 ID 集合和方向一致 |
| G-002 | parity | 查询有界路径 | 路径顺序、最大深度和找不到路径行为一致 |
| G-003 | parity | 查询 depth=1/2 的子图 | `core_node`、邻居和边集合一致；中心 status 过滤可验证 |
| G-004 | parity | 沿 FOLLOWS 获取 context chain | 顺序、环路处理和租户过滤一致 |
| G-005 | live | 高度节点执行 `search_by_kneighbor` | 服务端结果受 `max_degree`、`skip_degree`、`limit` 约束 |
| G-006 | parity | 子图中存在跨租户负例边 | 不得穿越租户边界 |

### 4.5 元数据、全文和向量检索

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| R-001 | parity | metadata `=`、`in`、`contains` | 返回相同节点集合 |
| R-002 | parity | metadata `starts_with`、`ends_with`、比较运算 | 结果与统一过滤语义一致 |
| R-003 | parity | `filter` 的 `and/or` 表达式 | 不得被 `**kwargs` 静默忽略 |
| R-004 | parity | `knowledgebase_ids`/cube 过滤 | 结果、空列表和默认租户行为一致 |
| R-005 | live | 多关键词全文检索 | 每个关键词的组合语义和排序规则必须明确；不能只验证第一个词 |
| R-006 | parity | query 含引号、换行、中文和 Gremlin/Cypher 特殊字符 | 不发生注入、截断或查询语法错误 |
| R-007 | parity | Qdrant vector index 检索 | top-k、scope、status、tenant、threshold 和返回字段一致 |
| R-008 | parity | Milvus vector index 检索 | 与 Qdrant 使用同一 `BaseVectorIndex` 结果契约 |
| R-009 | mock/live | 不配置 vector index | 图 CRUD 仍可用；向量检索返回值和告警行为必须在文档中明确 |
| R-010 | live | 向量维度不匹配、集合不存在或服务不可用 | 返回可诊断错误，不伪造召回结果 |

### 4.6 导入导出和数据迁移

| ID | 层级 | 操作 | 预期 |
| --- | --- | --- | --- |
| M-001 | mock | 导出 fixture 节点和边 | 输出统一 `{nodes, edges}` 结构，分页和过滤语义可解释 |
| M-002 | parity | 导出时排除 deleted 节点 | 节点和边过滤一致，不留下孤立边 |
| M-003 | parity | 导出后导入到空 HG graph | 节点、边、metadata 和 embedding 可恢复 |
| M-004 | migration | Neo4j 动态关系类型转换为 HG 固定边标签 + `relation_type` | 转换规则有明确字段映射，不能直接复制原始数据库记录 |
| M-005 | migration | `PRIMARY_KEY` 旧 Schema 数据迁移到 `CUSTOMIZE_STRING` | 先导出，再在新 graph 初始化 Schema，再导入；不原地覆盖 ID 策略 |
| M-006 | live | 导入后执行节点、边、全文和向量抽样读取 | 迁移后的结果与源数据规范化结果一致 |

## 5. 统一结果规范化

Neo4j 和 HugeGraph 的原始响应不作为直接比较对象。测试比较前必须：

1. 节点统一为 `{id: str, memory: str, metadata: dict}`。
2. 边统一为 `{source: str, target: str, type: str}`。
3. 将 Neo4j 动态关系类型与 HG `relation_type` 转换为同一个 `type` 字段。
4. 去除数据库特有字段、响应包装、内部数据库 ID 和未请求的 embedding。
5. 节点集合按 `id` 排序；边集合按 `(source, target, type)` 排序。
6. 向量结果按 `(id, score)` 比较，允许在文档中声明浮点误差范围；不能只比较返回数量。
7. 对空结果、未找到、参数错误和服务错误分别比较，不将所有异常统一成空列表。

## 6. 推荐运行方式

### 6.0 先验证 fixture 本身

在连接任何数据库前，先确认测试数据没有损坏：

```bash
python3 -m json.tool tests/fixtures/hugegraph_neo4j_compatibility.json >/dev/null
python3 -c 'import json; from pathlib import Path; d=json.loads(Path("tests/fixtures/hugegraph_neo4j_compatibility.json").read_text()); ids={n["id"] for n in d["nodes"]}; assert len(ids) == 9; assert len(d["edges"]) == 5; assert {n["tenant"] for n in d["nodes"]} == {"tenant-a", "tenant-b"}; assert all(e["source"] in ids and e["target"] in ids for e in d["edges"]); assert all(next(n["tenant"] for n in d["nodes"] if n["id"] == e["source"]) == e["tenant"] == next(n["tenant"] for n in d["nodes"] if n["id"] == e["target"]) for e in d["edges"]); print("fixture OK: 9 nodes, 5 edges, 2 tenants")'
```

预期输出：`fixture OK: 9 nodes, 5 edges, 2 tenants`。这一步只验证数据文件，不代表 HugeGraph 或 Neo4j 已经通过。

### 6.1 当前离线测试

```bash
uv run --with pytest pytest \
  tests/graph_dbs/test_hugegraph_backend.py \
  tests/graph_dbs/test_hugegraph_graphrag.py \
  tests/vec_dbs/test_index.py \
  tests/api/test_hugegraph_config.py -q
```

该命令只能证明 mock/unit 层行为，不能证明 HugeGraph 服务兼容。

### 6.2 当前 live 测试

```bash
MEMOS_RUN_HUGEGRAPH_LIVE=1 \
HUGEGRAPH_HOST=127.0.0.1 \
HUGEGRAPH_PORT=18080 \
QDRANT_HOST=127.0.0.1 \
QDRANT_PORT=6333 \
uv run --with pytest pytest tests/graph_dbs/test_hugegraph_live.py -q
```

运行前必须确认：

- HugeGraph graph 已存在；
- `Memory` 和 `MEMORY_RELATION` Schema 已创建；
- `Memory` 使用 `CUSTOMIZE_STRING` ID 策略；
- graphspace 配置与服务器实际部署一致；
- Qdrant/Milvus 集合已创建且向量维度匹配；
- live 测试使用独立 tenant/ID，并在 `finally` 中清理。

当前 live 测试本身仍不足以覆盖 B1–B8，应使用本文档矩阵和 fixture 扩展验证。

### 6.3 验证记录要求

每次执行至少记录：

- 后端类型、版本、graph、graphspace 和向量后端名称；
- 测试数据 fixture 名称；
- mock/live/parity 测试类别；
- 通过、失败、跳过数量及失败用例；
- 是否发生数据清理；
- 失败是 provider 逻辑、SDK 响应、Schema、网络还是外置向量服务问题。

禁止记录密码、API key、token、原始用户数据或完整向量内容。

## 7. 完成判定

本文档对应的兼容性工作只有在以下事实全部具备时，才能称为“测试闭环”：

1. 结构测试和上层调用契约测试通过。
2. 同一 fixture 在 Neo4j/HugeGraph 上的核心 CRUD、租户、图遍历、检索和迁移结果完成规范化比较。
3. 至少一次真实 HugeGraph + Schema + 外置向量服务验证通过。
4. B1–B8 每项都有通过证据、明确阻断项或有意设计差异，不能静默忽略。
5. 测试命令、fixture、环境变量和清理方式可以被其他开发者复现。

在上述条件满足前，MR 只能描述为“HugeGraph provider integration/adapter”，不能描述为“Neo4j drop-in replacement”。
