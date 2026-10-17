# memos-mcp — MemOS MCP 网关

把自部署的 MemOS 以 **MCP** 暴露给其他使用者。别人不用装 Python、不用装 fastmcp，
填一个 URL 和 token 就能接。

```
使用者（Claude Code / Cursor / 任意 MCP 客户端）
        │  POST /mcp   Authorization: Bearer <token>
        ▼
   memos-mcp 网关 :8003
        │  HTTP
        ▼
   MemOS 服务 :8000        ← 自部署的 MemOS（Neo4j + Qdrant）
```

这个两层结构和官方《MemOS MCP集成指南》里写的自部署架构一致
（MCP 服务器 → Server API），工具集按自部署能映射的部分做了对齐。

---

## 工具集（5 个）

严格对齐官方云 MCP [`@memtensor/memos-api-mcp`](https://www.npmjs.com/package/@memtensor/memos-api-mcp)
v1.1.2 里**本部署能映射的部分**——工具名、参数名、返回字段都保持一致，
使用者将来切云版时提示词和配置几乎不用改。

| 工具 | 作用 | 云版端点 | 本部署端点 |
|---|---|---|---|
| `add_message` | 保存对话消息并提取新记忆 | `/add/message` | `/product/add` |
| `search_memory` | 语义检索记忆 | `/search/memory` | `/product/search` |
| `delete_memory` | 按 id 删除记忆 | `/delete/memory` | `/product/delete_memory` |
| `add_feedback` | 提交反馈 / 修正 | `/add/feedback` | `/product/feedback` |
| `get_user_profile` | 获取用户画像（事实 / 偏好 / 工具经验） | `/get/memory` | `/product/get_memory` |

**云版另外 5 个工具没有提供**，因为它们是 knowledgebase 相关的
（`/create/knowledgebase`、`/add|get|delete/knowledgebase-file`、`/delete/knowledgebase`），
本部署的 29 条路由里没有任何对应端点，做不了。

`search_memory` 的返回结构也按云版组织：

```json
{
  "memory_detail_list":       [{ "memory_key": …, "memory_value": …, "relativity": …, "memory_id": … }],
  "preference_detail_list":   [{ "preference": …, "preference_type": …, "relativity": … }],
  "tool_memory_detail_list":  [{ "tool_value": …, "relativity": … }]
}
```

> `memory_id` 是我们额外加的——云版靠 `search_memory` 的结果拿 id 再删，有这个字段更省事。

---

## 接入方式

### 1. 拿到 token

找管理员要一个 token。**token 就是身份**：它决定了你的记忆空间，
不需要也不应该在工具参数里传 `user_id`。

### 2. 在你的 MCP 客户端里加一条配置

Claude Code（`.mcp.json` 或 `~/.claude.json`）：

```json
{
  "mcpServers": {
    "memos": {
      "type": "http",
      "url": "http://<网关地址>:8003/mcp",
      "headers": { "Authorization": "Bearer <你的 token>" }
    }
  }
}
```

Cursor / Cline / 其他客户端同理，填 URL + Authorization 头即可。

### 3. 验证

连上以后应该能看到 5 个工具。让 agent 调一次 `search_memory`，
返回空列表也是正常的（还没有记忆）。

---

## 运行

网关是一个独立的 Python 进程，只依赖 `fastmcp`：

```bash
export MEMOS_API_BASE_URL=http://localhost:8000
export MEMOS_TENANTS='tok-alice:alice,tok-bob:bob'
python3 memos_gateway.py --transport http --host 0.0.0.0 --port 8003
```

`--transport stdio` 可以在本地以 stdio 方式挂进客户端调试。

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MEMOS_TENANTS` | 空（必填） | token → user_id 映射，`tok-a:alice,tok-b:bob` 或 JSON 两种写法皆可 |
| `MEMOS_API_BASE_URL` | `http://localhost:8000` | 后端 MemOS 服务地址 |
| `MEMORY_CALL_LOG_DIR` | `/var/log/memos-gateway` | 调用日志落盘目录 |
| `MEMORY_SERVICE_NAME` | `MemoryService` | 对客户端展示的服务名 |
| `MEMOS_TIMEOUT` | `120` | 单次 REST 调用超时秒数 |
| `MEMOS_HOST` / `MEMOS_PORT` | `0.0.0.0` / `8002` | HTTP 监听地址 |
| `MEMOS_ALLOWED_CUBES` | 空 | cube 白名单；默认每个租户只用自己的 `user_id` 当 cube |
| `MEMORY_QUERY_PREFIX` | 空 | 检索侧 query 前缀，嵌入模型要求查询与文档两侧对称时用 |

### 账号怎么配

`MEMOS_TENANTS` 一行一个 `token:user_id`，逗号分隔：

```
memos-xxxxxxxx:demo-agent
memos-yyyyyyyy:demo-agent        ← 同一个 user_id = 共用一份记忆
memos-zzzzzzzz:demo-agent-zhang  ← 不同 user_id = 各自独立
```

**一个 token 一个人**，不要多人共用一个——这样以后谁不用了可以单独作废，不影响别人。

> ⚠️ **空间一旦分开就合不回来了。** 记忆是按 `user_id` 存的，后端没有跨空间迁移的接口。
> 决定共用还是分开，最好在对方开始用之前定。

改完 `MEMOS_TENANTS` 必须重启进程：环境变量不会热更新。

### 改网关代码

改 `gateway/` 下对应模块（入口仍是 `memos_gateway.py`），重启进程即生效。
本地可以先跑契约锁，不需要 fastmcp 与后端：

```bash
python3 test_gateway_contract.py
python3 test_gateway_tools.py
python3 test_gateway_audit.py
```

改了 `gateway/mcp_api/tools.py` 里的工具描述（描述就是 prompt）还要跑
`prompt_regression_test.py`，它从真实网关拉 `tools/list` 再让模型决策。

### 记忆隔离怎么保证的

`user_id` 从 Bearer token 解出来（`StaticTokenVerifier` 的 claims），
**不是工具参数**，所以模型既看不到也传不了。跨租户隔离实测过：
alice 写入的记忆，bob 检索命中 0 条；拿别人的 id 去删会被整批拒绝。

### 调用日志（度量谁在用、用了多少）

每次工具调用追加一行 JSONL，落在 `MEMORY_CALL_LOG_DIR` 下：

```
calls-YYYYMMDD.jsonl
```

字段：`ts / tool / tenant / session_id / case_like / ms / ok / err / result_bytes / input / output`。
**记工具入参和返回正文**（超 16KB 截断并打 `truncated`）；**不记 token 原文**（HTTP 层仍是掩码）。

```json
{"ts":"2026-09-28T16:00:00+0000","tool":"search_memory","tenant":"demo-client","session_id":null,"case_like":null,"ms":758,"ok":true,"err":null,"result_bytes":92,"input":{"query":"…"},"output":"{\n \"memory_detail_list\": []\n}"}
```

> ⚠️ **只增不删**。代码里没有任何清理逻辑。任何人工清理**必须先确认**。
> 落盘会 `flush + fsync`；写失败会计数并打 warning，**不会影响工具调用**。

---

## 已知限制

1. **写入内容会被改写**：本部署在入库前会用 LLM 把内容改写成第三人称叙述，
   所以读回来的不是你写进去的原文。这是后端行为，不是网关做的。
2. **删除是软删除**：记录不再出现在检索结果里，但仍可按 id 查出（状态 `deleted`）。
3. **没有知识库能力**：见上文，云版的 5 个 KB 工具在这里没有对应实现。
4. **无更新接口**：要「修改」一条记忆，只能删掉旧的再写新的（和云版一样，
   云版也没有 update 工具）。
5. **token 明文放在环境变量里**：小规模内部使用可以接受；
   如果要更严，改成 Secret 注入即可。
6. **⚠️ TODO：`session_id` 的语义与"会话"不符**（待处理）：
   网关把客户端传的 `conversation_first_message` 折算成 `conv_<sha1[:16]>`
   （`gateway/domain/session.py`，注释自称"软信号"）。当客户端用**固定模板**作为首消息时，
   **所有同模板任务会算出同一个 session_id**，无法用它区分具体任务。
   - **影响**：后端仅把它用作**检索优先级软信号**（`multi_mem_cube/single_cube.py`
     的 `search_priority`，非硬过滤）——同类任务记忆互相优先，功能上尚可接受。
   - **待办**：评估是否把哈希输入扩为 `first_message + "\n" + messages[0].content`。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `memos_gateway.py` | 启动入口 |
| `gateway/app.py` | 组装：配置 → 租户 → 后端 → 记忆服务 → 审计 → FastMCP |
| `gateway/service.py` | 5 个工具的业务（写入 / 检索 / 删除 / 反馈 / 画像） |
| `gateway/backend.py` | `ProductClient`：调后端 REST、消化静默失败 |
| `gateway/domain/` | 调用方、租户、会话、云版字段形状 |
| `gateway/audit/` | JSONL sink、工具埋点、HTTP/RPC 中间件 |
| `gateway/mcp_api/tools.py` | MCP 薄适配（描述是 prompt，改前必跑回归） |
| `gateway/mcp_api/http.py` | `/` 落地页、`/health` |
| `gateway/identity.py` | token → Caller |
| `test_gateway_contract.py` | 工具名 / 签名 / docstring / 对外文案锁 |
| `test_gateway_tools.py` | 工具 payload 与失败语义（不连后端） |
| `test_gateway_audit.py` | 审计截断 / JSONL fsync |
| `prompt_regression_test.py` | 工具描述的模型行为回归 |
