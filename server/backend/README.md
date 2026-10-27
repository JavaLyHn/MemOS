# Dashboard 独立后端

当前可部署交付以 [DELIVERY.md](DELIVERY.md) 为入口，包含跨平台启动、完整上游补丁、范围与验收摘要。下方任务分阶段说明和 TASKxx 报告保留历史状态，早期 sample/端口和旧测试数量不代表当前交付状态。

权限采用平台与项目两层授权，详见 [AUTHORIZATION.md](AUTHORIZATION.md)：账号管理仅平台管理员可用；项目 owner 管理本项目成员与邀请；viewer/editor 可查看本项目成员并退出自己。`/admin/` 路径前缀不表示所有接口都仅平台管理员可用。OpenAPI 的逐接口说明与 `x-authorization` 同步记录此规则。

已实现独立服务、统一响应与错误、MemOS 连接检查、`GET /api/meta`，以及六标签记忆列表、详情、软删除、恢复、操作回执和失败重试。调用日志、按日用量和任务06项目生命周期也已实现。项目列表、创建、更新、选中、停用、归档和恢复使用真实 SQLite 持久化；任务07账号、任务08成员、任务09邀请均已实现。详见 `TASK07-RESULT.md`、`TASK08-RESULT.md`、`TASK09-RESULT.md`。

任务12 Prompt 与任务13图谱/模型已交付，详见 [TASK12-RESULT.md](TASK12-RESULT.md)、[TASK13-RESULT.md](TASK13-RESULT.md)。真实抽取需要部署 `patches/task12-upstream-prompt-runtime.patch` 中的上游内部修复并重启上游；本机已应用和验证。知识库任务10、11按用户要求冻结当前实现，不宣称补齐全部原验收项。

主前端5274继续连接原始 Mock，辅助5276用于真实服务联调。请不要为显示 `live` 标记修改 `.env.local` 或停止 Mock。

## 启动

要求 Python 3.11 或更新版本。在仓库根目录运行。使用独立 Python 环境安装：

```sh
python -m pip install -r server/backend/requirements-dev.txt
python -m server.backend --host 127.0.0.1 --port 5281
```

依赖已经安装时可以直接启动。`pnpm backend` 和 `pnpm backend:test` 使用当前 PATH 中的 Python，需要先激活相应虚拟环境。

当前 Windows 环境的直接启动命令：

```powershell
cd D:\MemOS\dashboard
$env:DASHBOARD_PROJECTS = 'issue3-project-a:issue3-project-a;issue3-project-b:issue3-project-b'
$env:DASHBOARD_DEFAULT_PROJECT_ID = 'issue3-project-a'
$env:DASHBOARD_UPSTREAM_TIMEOUT_SECONDS = '10'
& D:\MemOS\.venv\Scripts\python.exe -m server.backend --port 5281
```

该命令在前台运行，按 Ctrl+C 停止。当前项目还提供后台启停脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\MemOS\setup\Start-Backend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File D:\MemOS\setup\Stop-Backend.ps1
```

本地辅助脚本位于 Dashboard 仓库外，属于当前工作区环境；可移植的交付入口是 `python -m server.backend`。默认只绑定本机，不启用自动 reload。后端启动不要求 MemOS 已在线；连接失败会在元信息接口中明确返回。

## 配置

配置来自进程环境变量，示例见同目录 `.env.example`；程序不自动加载模型密钥文件。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DASHBOARD_UPSTREAM_URL` | `http://127.0.0.1:8000/` | MemOS 根地址，可带部署路径前缀；禁止用户名、密码、查询参数和片段 |
| `DASHBOARD_MODEL_TIMEOUT_SECONDS` | `120` | Prompt生成与调试的总截止秒数，大于0且不超过180秒；后端不持有模型密钥 |
| `DASHBOARD_UPSTREAM_TIMEOUT_SECONDS` | `3` | 本次健康请求的总截止时间，同时配置 HTTP 阶段超时；大于 0 且不超过 60 秒 |
| `DASHBOARD_PROJECTS` | 空 | `projectId:cubeId`，多个用分号分隔；种子访问范围；另允许本地操作员通过接口创建的持久项目 |
| `DASHBOARD_DEFAULT_PROJECT_ID` | 空 | 配置项目时必填；无有效项目偏好时的初始选择；详情按持久 cookie 上下文中的当前项目查询 |
| `DASHBOARD_DATA_DIR` | `.data` | 项目及偏好上下文 SQLite 保存目录；无种子配置也可创建首个项目 |

任务 01 不需要 Haiku、Embedding 或数据库密钥。内部 HTTP 客户端不读取系统代理变量，不跟随重定向，不做隐式重试；远端 MemOS 需要网络直达。

## 接口和含义

| 接口 | 用途 |
|---|---|
| `GET /health` | 后端进程存活检查，不访问上游，仍使用统一响应 |
| `GET /api/meta` | 每次真实访问 MemOS `/health`，校验服务身份和契约后返回运行信息 |
| `GET /api/dashboard/project/dict` | 当前实例可访问的活跃项目；仅本上下文当前项目标为 ENABLED |
| `POST /api/dashboard/project/memory/list` | 六标签、项目范围、组合筛选与原生分页 |
| `POST /api/dashboard/project/memory/detail` | 当前上下文项目内按同一 memoryId 读取详情 |
| `GET /docs` | 本阶段实际注册接口的调试文档；完整 Dashboard 规格仍以仓库根 `openapi.json` 为准 |

正常元信息响应示例：

```json
{
  "code": 0,
  "data": {
    "mode": "live",
    "service": "memos-dashboard-backend",
    "health": {
      "status": "healthy",
      "service": "memos",
      "version": "1.0.1",
      "contract_version": 2
    },
    "keyPrefix": "sk-",
    "tools": [
      { "name": "add_message", "title": "写入记忆" },
      { "name": "search_memory", "title": "检索记忆" },
      { "name": "get_user_profile", "title": "读取画像" },
      { "name": "delete_memory", "title": "删除记忆" },
      { "name": "add_feedback", "title": "提交反馈" }
    ],
    "authEnabled": true
  },
  "message": "success"
}
```

`live` 表示这个后端真实探测了 MemOS，**不代表整个 Issue 已经完成**。`tools` 是既有 MCP 网关协议的工具目录，`keyPrefix` 是控制台密钥格式约定；本阶段未实现密钥管理或网关工具代理。默认 `authEnabled=true`，业务接口要求真实登录会话，并按平台管理员或项目成员角色校验。`live` 本身仍不代表权限配置或全部模块已验收。只有显式设置 `DASHBOARD_AUTH_ENABLED=false` 才启用历史本机操作员模式；隔离的旧模块夹具也明确指定此模式。

健康信息仅保留上述四个字段；不透传上游配置、密钥、异常详情和任意扩展字段。健康响应体最多读取 64 KiB，响应不缓存。请求指定 identity 编码，读取前拒绝压缩响应，避免先解压再检查大小。探测只证明 HTTP 可达和当前上游自报的进程状态，不能将其解读为 Neo4j、Qdrant、模型全部经过实时深度检查。

## 错误

错误均为 `{ "code": 非零值, "data": null, "message": "说明" }`，并返回对应 HTTP 状态。不会切换为假数据或复用上一次成功健康状态。

| 情况 | HTTP | code |
|---|---|---|
| 参数校验失败 | 400 | 40000 |
| 接口不存在（含未实现业务接口） | 404 | 40001 |
| 方法不支持 | 405 | 40000 |
| 上游 HTTP 异常、非 JSON、响应格式或契约不匹配 | 502 | 50200 |
| 上游连接失败或报告不健康 | 503 | 50300 |
| 上游超时 | 504 | 50400 |
| 未预期的内部异常 | 500 | 50000 |

仅接受 `service=memos`、`status=healthy`、非空版本和整数 `contract_version=2`。契约版本不兼容时不会报告成功；恢复上游后下一次请求即可恢复，无须重启后端。

## 测试与人工验证

```sh
python -m pytest server/backend/tests -q
python -m ruff check server/backend
python -m ruff format --check server/backend
pnpm verify
pnpm --package=@redocly/cli dlx redocly lint openapi.json
```

单元测试使用 httpx MockTransport，验证成功与故障，不调用真实模型、不写记忆、不依赖 Docker。CLI 启动验证使用子进程。

当前环境可分别打开：

- 后端元信息：http://127.0.0.1:5281/api/meta，应为 `code=0`、`mode=live`，包含实际 MemOS 健康信息。
- 后端进程检查：http://127.0.0.1:5281/health。
- 现有前端元信息：http://127.0.0.1:5274/api/meta，仍应为 `mode=sample`。

可以用单独端口启动一个指向不存在上游的后端实例来验证 503，不需要停止当前真实 MemOS 或 Mock。任务 01 的实际验收结果另见同目录 `TASK01-RESULT.md`。

## 任务 02 的查询口径

只读 activated 记忆；先筛选、计数，再分页。列表正文最多 500 字符加省略号，详情保留全文；不透传 embedding、sources、history。日期按 UTC 自然日处理，时间戳须带时区。图记忆搜索遵循上游大小写敏感子串语义，画像搜索不区分大小写。

`knowledgeBaseId` 匹配真实图元数据的 `knowledgebase_id`、`knowledge_base_id`、`knowledgebase_ids`，没有关联的记录不命中。画像按实例创建时间排序和过滤，每个有效字段是一条可定位的记忆。部署时需要同时安装本任务新增的上游画像只读接口与可选事件类型过滤参数。

真实请求示例：

```powershell
$query = @{ projectId='issue3-project-a'; memoryDetailType='text_mem'; pageNum=1; pageSize=10 }
Invoke-RestMethod http://127.0.0.1:5281/api/dashboard/project/memory/list -Method Post -ContentType 'application/json' -Body ($query | ConvertTo-Json)
```

当前工作区的可重复真实验收：`D:\MemOS\.venv\Scripts\python.exe D:\MemOS\setup\verify_task02.py`。默认只读已保存的测试标识，`--seed` 才允许补建独立测试数据。完整结果见 `TASK02-RESULT.md`。主前端 5274 保持 Mock，独立验收前端使用 5276。

## 任务 03：软删除和恢复

`POST /api/dashboard/project/memory/delete`、`/restore` 接受 `projectId`、`memType`、`memory_ids` 和可选 `operationId`。先检查全部目标的项目、类型和状态，再逐项执行。删除保留正文和向量，画像只操作单个字段；普通记忆需图与向量状态双边确认。

全部确认才返回 code=0。部分失败返回 code=50301，data 内保留确认数量、operationId 和逐项结果。`GET /api/dashboard/project/memory/operation?projectId=...&operationId=...` 查询进度；查询成功仍须检查 data.state。`POST /api/dashboard/project/memory/retry` 接受 projectId、operationId，重试未确认项。恢复和重试目前使用 API，没有修改前端增加新界面。

部署需要同步上游生命周期路由、MetadataStore 锁、普通读取可见性修正和后台补偿。单独更新 Dashboard 不能提供这些语义。Dashboard 已接入账号会话与项目角色；上游控制面端口仍限可信本机/内网使用。浏览器写请求检查显式配置的控制台 Origin，不能绕过 Dashboard 直接公开无鉴权上游。

完整实现、真实进程中断与向量连接故障证据、已有基线测试失败说明见 `TASK03-RESULT.md`。仅本次独立测试记录经过删除与恢复，原有 Task01/02 数据保留。

## 任务 04：调用日志

已实现 `/api/dashboard/log/list` 和 `/api/dashboard/log/detail`。安装 `requirements.txt` 中新增的固定依赖 `orjson==3.11.4`。通过 `DASHBOARD_AUDIT_GATEWAY_DIR` 显式指定网关审计目录；控制台来源默认保存在 `DASHBOARD_DATA_DIR/audit`，可通过 `DASHBOARD_AUDIT_CONSOLE_DIR` 覆盖。当前本机启动脚本配置为 `D:/MemOS/.local/audit`。

仅导入 `calls-*.jsonl`、`console-*.jsonl` 及数字后缀轮转文件（如 `.jsonl.1`）；协议、检索诊断、备份、临时和压缩文件不计为调用。增量索引位于 `DASHBOARD_DATA_DIR/audit.db`；索引支持重启与事务回滚，坏行诊断保存在 `audit_rejects`（仅代次、字节位置、原因，不存原始坏行），可按 reason 分组计数。

来源、主体、事件、状态、关键词、UTC 时间和分页筛选先于计数与分页执行。未知筛选参数返回 400；不可用来源返回 503，不能返回空列表假成功。详情使用当前持久项目上下文，列表刷新导入索引。日志查询本身不追加控制台业务日志。

历史 Token 缺失填 0、耗时缺失为 null；异步按来源、租户、callId 合并。当前真实网关没有异步关联记录，这部分经独立 JSONL/HTTP 夹具验证。完整配置、性能计时、真实链路与边界见 `TASK04-RESULT.md`。主前端 5274 保持 Mock，真实日志验收页为 http://127.0.0.1:5276/cn/requests 。任务 05 用量聚合的最新交付口径见下节。

## 任务 05：用量聚合

已交付 `POST /api/dashboard/usage/query`，复用日志同一 `AuditService` / `audit_calls` 索引，仅统计 gateway。北京时间固定UTC+8切天、空日补0、默认当月1日至今天、最多366天；日期参数仅YYYY-MM-DD。缺时间的历史行不进入日期统计，缺token为0。

`projectId`省略/null/空白/all只覆盖当前配置种子与本地操作员创建的活跃项目；配置撤销的数据库旧项目不再进入统计。具体未授权项目404、无范围或来源不可用503。认证模式还按当前账号的成员关系限制范围，平台管理员可访问配置允许及本地创建项目。非空apiKeyId明确400，不静默忽略。

页面次数与`summary.totalCalls`均仅addMessage+searchMemory；失败/pending等各逻辑调用算一次，异步终态更新token不重复计次。chat/extractMemory提供真实token，rerank提供次数和token；未知事件/console排除。summary.totalTokens涵盖五个已知分组。includeDailyDetails=false返回空dailyStats及同一summary。

专项测试与真实HTTP验收见[TASK05-RESULT.md](TASK05-RESULT.md)，只读验收脚本`D:/MemOS/setup/verify_task05.py`。任务06—09已交付，知识库等模块继续依实施顺序推进。

## 任务06 项目工作区

- `POST /api/dashboard/project/list`：`pageNum/pageSize`，返回 `records/total`，包含停用与归档项目以便恢复。
- `create`：`name/description`，可选 `isMultiView`；服务端生成不可变 ID 和对应上游 namespace。
- `update`：`id` 加至少一个显式非 null 可写字段。活跃项目 `status=ENABLED` 为选中；停用项目同一请求只重新启用，不自动切换。`DISABLED` 为停用。
- `delete/{id}`：可恢复归档；`restore/{id}` 恢复；`revoke/{id}` 为归档兼容别名。都不删除上游记忆。
- 认证模式使用 `memos_session` 及其持久项目上下文；不同登录会话独立选择，重启保留。历史 `memos_project_context` 只在显式关闭鉴权的隔离模式中使用，不是登录凭证，也不能给认证会话指定其他项目。
- 字典排除停用/归档项目，记忆、日志和用量显式项目查询同步拒绝；当前项目失活时回退到其他活跃项目。
- 认证模式返回真实有效项目角色；平台管理员具有项目管理能力。网关密钥状态联动属于后续密钥任务，不能根据既有前端提示认定已实现。
- 独立真实页面为 `http://127.0.0.1:5276/cn/projects`。既有前端在归档当前项目时曾出现表格缓存滞后，重新载入可显示真实状态；遵守 `src/` 零变更要求，未改动该前端行为。

## 任务07—09 登录、账号、成员与邀请

默认启动要求登录，先用本地 CLI 初始化唯一首个管理员（环境变量使用上述相同数据目录与项目映射）：

```powershell
& D:\MemOS\.venv\Scripts\python.exe -m server.backend.bootstrap memos-admin --bootstrap
```

命令交互式读取12—256字符密码，不把密码放进参数。需要自动随机密码时可追加 `--credential-file`，目标文件须不存在。后续本地新增账号使用相同命令去掉 `--bootstrap`，需要平台管理员时显式加 `--admin`；现有账号密码不会被此命令覆盖。Windows 部署须限制凭据文件 ACL，本机初始化文件已限制为当前用户。

本机已完成初始化。登录入口 http://127.0.0.1:5276/__login ，账号 `memos-admin`，随机密码只保存在 `D:/MemOS/.local/dashboard-admin.json`。使用真实控制台5276；5274保持Mock。登录后“项目与成员→用户”显示真实账号；团队项目“成员”进入成员/邀请管理。

| 配置 | 默认值 | 语义 |
|---|---|---|
| `DASHBOARD_AUTH_ENABLED` | `true` | 默认启用会话鉴权；false仅用于显式本机操作员隔离场景 |
| `DASHBOARD_SESSION_TTL_SECONDS` | `86400` | 会话秒数，60—2592000；退出、禁用和删除即时撤销，不通过重新启用复活 |
| `DASHBOARD_ALLOWED_ORIGINS` | localhost/127.0.0.1/[::1] 的5274、5276、5281 HTTP来源 | 可用分号配置明确HTTP/HTTPS来源，不含路径或凭据；HTTPS下Cookie带Secure |

- `GET/POST /__login`、`GET/POST /__logout` 是后端HTML表单，沿用现有Vite代理。CSRF、Origin、严格同源重定向和登录失败限制均在服务端执行。页面Referrer-Policy为same-origin，避免no-referrer导致浏览器表单Origin:null；跨源不发送引用地址，CSP限定form-action self。
- `/api/auth/me` 使用camelCase；`/admin/accounts` 与成员列表的账号字段使用snake_case。所有JSON业务响应保持统一信封；HTML表单成功303跳转，不虚构200。
- 管理员维护账号；owner/管理员管理团队成员、邀请及项目生命周期；editor可执行记忆写操作；viewer只读，也可选中有权访问的活跃项目。权限变更在下一次请求即时生效，全项目用量也限制成员范围。
- 每个账号拥有独立个人空间。团队成员可添加、改角色、移除及自行退出；个人空间不提供团队成员/邀请写操作。最后有效管理员、最后有效团队owner不能被降级、移除、禁用或删除；并发操作同样受事务约束。
- 邀请通过 `POST /admin/tenants/{tenantId}/invites` 创建，角色viewer/editor/owner，有效期默认168h，最多30天。只在创建返回 `path`；库和列表不保存/返回明文token。落地 `/__login/invite/{token}` 支持登录账号接受或新账号注册接受；原子单次使用，已有成员返回409且不降级、不消费邀请。
- 账号删除清理个人控制空间、成员和会话，团队项目保留；邀请创建者/使用者引用清空且已使用状态保留。没有P3密钥表时不声称已验证网关密钥联动；不会删除上游记忆。
- `python -m pytest server/backend/tests -q` 覆盖这些功能及既有任务回归。真实环境验收脚本 `D:/MemOS/setup/verify_task07_09.py` 只操作明确命名的空测试资源，不写删真实记忆或调用模型。

## 任务 14：接口密钥（P3 密钥）

「密钥即项目」：dashboard 界面签发的接口密钥代表项目本体，网关侧身份就是 `user_id = cube_id = <项目 id>`，调用与既有租户一样落在项目自己的记忆空间，审计照常归因。

密钥存于 control.db 的 `api_keys` 表（明文存 `token`、存 `token_hash`，软撤销保留行）。每次 create / revoke 在同一事务里把 active 密钥清单原子写入网关配置文件——**接口成功返回 ⟺ 文件已写入**，写文件失败随事务回滚并返回 503，密钥不落库（绝不假成功）。

配置与流程：

| 配置 | 默认 | 语义 |
|---|---|---|
| `DASHBOARD_GATEWAY_KEYS_FILE` | 空 | 网关交付路径（tenants.conf）；为空时 create/revoke 返回 503，list/copy/rename 不受影响 |

- `setup/Start-Backend.ps1` / `setup/Restart-Backend.ps1` 已支持 `-GatewayKeysFile`（默认 `D:/MemOS/upstream/deploy/mcp-gateway/tenants.conf`），Restart 会透传旧记录值，旧记录缺该字段时回退默认。
- 后端每次启动会按库内 active 集合**单向重写**该文件（自愈；写失败只告警不阻断启动，后续写操作如实报错）。手工放进去的 token 会被拭除——手工管理的密钥请走 `MEMOS_TENANTS`。
- 已升级网关在每次鉴权前检测 `MEMOS_TENANTS_FILE` 的变化：创建后下一请求可用，撤销后下一请求401，无需重启。首次部署自动重载代码需要重启一次；环境变量变更仍需重启。损坏、冲突、待确认或不可读文件暂时禁用文件密钥，确认发布后自动恢复，独立环境变量密钥不受影响。

密钥明文保存在本地 control.db 与网关配置文件（gitignore 范围内，无 KMS 不加密）；列表/复制仍按契约完整返回且仅 owner/platform admin 可见。自动重载不取消已经授权执行中的请求。当前验收见 `GATEWAY-RELOAD-RESULT.md`；`TASK14-RESULT.md` 中重启生效的描述保留为升级前历史记录。



## Task12/13最新专项验收（2026-10-27）

复核发现的合法空数组误判raw、规范类型绕过筛选两项问题已修复。280项后端测试、108项上游相关测试及新的真实模型/图谱同ID验证通过。上游内部补丁已更新，不能只部署Dashboard适配器。当前5276用于真实服务验证，5274仍为sample；详见[TASK12-13-REPAIR-2026-10-27.md](TASK12-13-REPAIR-2026-10-27.md)。知识库保持既有实现，未推进任务16。


## Task14独立复核修复完成（2026-10-27）

5项复核问题已关闭，当前以[TASK14-RESULT.md](TASK14-RESULT.md)的新验收为准。287项后端测试和单轮隔离真链路通过。网关补丁新增发布锁/pending协议，需与Dashboard一同部署；共享配置目录要支持协调锁。证据旧25条已归档，当前task14-live.json为20条单轮完整成功记录。安全重演入口为`python -m server.backend.acceptance.task14_driver --root D:/MemOS`，每轮新建项目、只清理本轮key，并真实重启后端/网关。知识库和任务15/16不在本轮变更范围。


## 2026-10-27 最终环境与验收

主站 http://127.0.0.1:5274 现在连接真实后端5281（live），Mock5280已停止，5276辅助真实前端保留。不要用历史Start-Dev输出中的sample提示判断当前连接。已有基础服务运行后，可执行 `powershell -NoProfile -ExecutionPolicy Bypass -File server/backend/acceptance/start_live.ps1` 切换主站，无需改.env.local。登录入口改用 http://127.0.0.1:5274/__login；管理员密码继续只在本机私有文件中读取。

Task15模板接口及前端限制见TASK15-RESULT.md；最终质量门、69操作矩阵、性能与故障证据及已知未实现项见TASK16-RESULT.md和TASK16-OPERATIONS.md。知识库保持用户冻结范围，模板页面仍为占位。


### Issue3固定接口补齐

额度概览、订阅周期、skillMD现已按Issue §2(3)提供固定成功返回，不再是404。额度0条计数/1000000容量/10知识库额度仅为展示默认值；订阅cycles为空，技能Markdown为空字符串，不实现真实计费或URL下载。知识库继续冻结。详见ISSUE3-FIXED-ENDPOINTS-RESULT.md。


### 普通账号注册

登录页可点击“注册账号”，或访问 /__login/register；输入账号、密码和确认密码，成功后回登录页。账号规则与现有身份系统一致，密码至少12字符；普通账号只拥有个人空间，加入其他项目需邀请。该页面由后端生成，不修改src/。验证及证据见REGISTRATION-RESULT.md。
