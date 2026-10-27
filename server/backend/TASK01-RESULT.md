# 任务 01 验收记录

状态：已完成。基础接口、独立代码检查及实际 HTTP 验证均已完成。仅涵盖设计文档实施顺序第 1 项。

## 交付内容

- 独立 FastAPI 后端，默认监听 127.0.0.1:5281；不导入 MemOS 模型、数据库或 Mock 模块。
- GET /health：本进程健康信息，使用 code/data/message 信封，不依赖上游在线。
- GET /api/meta：实时读取 MemOS /health，严格验证 memos / healthy / contract_version=2，白名单返回健康字段、live 来源、工具目录和密钥前缀。
- 统一处理业务异常、参数校验、404、405、上游故障和未预期异常；错误 data=null，不返回原始敏感错误。
- 总截止时间、HTTP 超时、64 KiB 健康响应上限、禁止重定向和隐式代理，生命周期关闭连接池。
- 可移植 Python CLI、依赖文件、环境变量示例、单元测试与使用文档。
- 当前工作区另提供 setup/Start-Backend.ps1 和 Stop-Backend.ps1，验证进程归属，重复启动不会替换已有服务。

## 修改范围

- 新建 server/backend/ 的实现、测试及文档。
- package.json 增加 backend 与 backend:test 两个命令，原命令不变。
- .gitignore 增加 Python 编译/测试缓存和虚拟环境排除项。
- openapi.json 增补元信息的 502/503/504/default 错误响应、统一错误 schema 和 authEnabled 说明。此前已有的纯排版差异仍在；本轮不把整个 diff 当成新增接口语义。
- src/、shared/、server/mock/ 与原始基线完全一致；未更改前端 .env.local 或代理目标。

## 已运行的检查

| 检查 | 结果 |
|---|---|
| 初始测试 RED | 后端实现不存在，测试收集明确失败 |
| 边界测试 RED | 总截止时间、响应体上限、启动配置脱敏三项先失败，再修复 |
| 后端 pytest | 56 passed |
| Ruff lint 与 format --check | 通过 |
| 真实 HTTP 验证 | 8 项通过，见下文 |
| 后台进程启停 | 启动、重复启动不重复创建、停止后重启均通过 |
| pnpm verify | 通过；保留原有大 chunk 提示 |
| Redocly lint | 通过；仍有缺 license、本地 server URL 两条既有 warning |
| git diff --check | 通过 |
| 对基线检查 src/、shared/、server/mock/ | 无改动 |

独立代码检查发现压缩响应先解压后限额的问题；已增加流式 gzip 等编码的读取前拒绝测试，先观察失败再修复。同时补齐 HTTP 协议异常到 502 的映射。新增 7 项回归最终全部通过；无遗留阻塞问题。压缩体测试验证其流根本未被消费，而不只是最终返回错误。

真实 HTTP 验证包括：真实上游健康一致、后端存活、未实现接口明确 404、真实连接失败 503 且本地存活仍正常、真实超时 504、前端与 Mock 仍为 sample、验证过程中前端配置未变、前端源码无差异。通过临时端口注入连接失败和慢响应，没有停止当前 MemOS、Mock 或网关。

当前环境的原始记录：D:/MemOS/.local/task01-runtime-verification.json；执行日志位于 Dashboard 的忽略目录 .data/task01-runtime-meta/。不将本地数据库、配置或真实审计文件提交到仓库。

## 亲自验证

1. 打开 http://127.0.0.1:5281/api/meta，应看到 code=0、mode=live，以及上游健康状态。
2. 打开 http://127.0.0.1:5281/health，应看到后端本身健康。
3. 打开 http://127.0.0.1:5274/api/meta，仍应是 sample；控制台仍使用 Mock。
4. 按 README 命令运行后端单元测试，或使用本地 setup/verify_task01.py 重跑真实 HTTP 验证。

## 边界

- live 只表示该后端使用真实 MemOS 探测，不能据此宣称记忆/日志功能完成。
- authEnabled=false；本阶段只有运行信息，未建立账号、项目或访问记忆数据的业务接口。
- MemOS /health 当前是进程自检，本任务不将它包装成数据库或模型的实时深度自检。
- 未调用付费模型，没有新增或删除记忆。
- 本轮结束后停在任务 01，不自动进入任务 02。
