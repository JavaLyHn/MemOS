# Task07 — P1 账号、登录会话与管理员交付结果

## 已交付

- 后端 `GET/POST /__login`、`GET/POST /__logout`，以及真实 `/api/auth/me`。现有Vite已代理这些路径，前端源码保持不变。
- 管理员账号分页/关键词搜索、更新显示名/管理员标记、禁用/启用、删除。JSON字段按规格保留snake_case；me为camelCase，完整响应由根OpenAPI校验。
- 密码采用16字节随机盐与scrypt；会话为32字节随机token，库中仅保存SHA256摘要、账号、到期时间和CSRF随机值。Cookie为HttpOnly/SameSite=Lax，HTTPS为Secure，默认24小时，范围60秒至30天。不同会话有独立持久当前项目，匿名偏好cookie不能替代登录。
- 每次请求重新检查会话和账号状态。退出撤销当前会话；禁用、删除撤销该账号所有会话，重新启用不会复活旧会话。默认开启鉴权，无任何公共默认密码或匿名管理员。
- 最后一个有效（未禁用）平台管理员不能被降级、禁用或删除。账号也是团队最后有效owner时，禁用/删除同样被拒；先转移所有权。BEGIN IMMEDIATE保护并发约束。
- 账号删除清理个人控制空间、成员及会话；团队项目不删除，邀请创建者/使用者引用置空，已消费状态保留。上游记忆不因账号删除被清空。P3密钥模块未实现，不宣称网关密钥清理或状态联动已经验收。

## 主要实现与故障修复

`identity_store.py`（账号/会话及约束）、`auth.py`（认证中间件、HTML与管理员API）、`bootstrap.py`（本地一次性初始化/账号创建）、`security.py`（显式Origin）、`settings.py`、`app.py`、`control.py`、`project_context.py`，以及记忆/日志/用量的请求级权限接线。

登录表单为8192字节上限、CSRF保护和同源跳转；数据库故障统一503且不透传详情。错误CSRF含Unicode时曾触发500，已先RED后修为403。真实浏览器发现no-referrer使表单Origin变成null，现改为same-origin并用浏览器证实；仍拒绝Origin:null，保留CSP form-action self和跨源来源限制。仅允许现有本机来源，或通过DASHBOARD_ALLOWED_ORIGINS显式配置HTTPS控制台来源。登录失败按来源限速，10次失败后等待5分钟；这不是外部身份提供商或完整企业SSO。

## 本机使用

打开 http://127.0.0.1:5276/__login ，账号 `memos-admin`；随机密码只保存在 `D:/MemOS/.local/dashboard-admin.json`，该文件已设置当前用户专有ACL。初始化前已做一致SQLite备份，位于 `D:/MemOS/.local/backups/before-task07-identity-*.sqlite`。登录后进入“项目与成员→用户”。主5274继续是Mock。

新部署使用 `python -m server.backend.bootstrap 用户名 --bootstrap` 交互设置首个管理员；本地新增账号去掉--bootstrap，需要管理员时加--admin；也可通过有效邀请注册。未提供公共随意注册或修改现有密码的接口。账号初始化仅能在空账号库执行一次。

## 共同验收证据（最终版本）

- 全后端 **229 passed，57.56秒**；其中任务07—09新增25项测试，保留任务01—06的204项回归，并显式标注旧隔离夹具的非认证模式。Settings与CLI默认均开启鉴权。
- Ruff check / format通过，47个Python文件；`pnpm verify`（类型、Lint、格式、构建）通过，保留原有chunk大小提示。
- Redocly：0错误、5条警告。原有license与localhost两条；新增3条因为HTML POST成功仅303跳转，没有2xx，按真实行为保留，不虚构200响应。根规格现为63条路径、69个HTTP操作，新增的是登录/退出/邀请落地各GET/POST。
- 一次继承主模型与思考强度的只读安全复核（无Astra、无额外实现agent），没有具体未解决问题。复核者独立运行当时22项身份测试通过；后续新增3项异常存储/HTTPS/浏览器表单策略回归由主控完成。
- `D:/MemOS/setup/verify_task07_09.py` 通过真实5281 HTTP执行登录、账号启停/删除、角色权限、成员增改移除及邀请创建/角色/注册接受/单次/撤销/过期，实际操作系统进程重启后保留会话、选中项目与已用邀请状态。最终合成项目 `proj_7ead9c61ba7a4775a41748cef8200ad7` 已可恢复归档，空的合成账号已删除；不写删真实记忆，不调用付费模型。
- Task01真实健康/连接故障/超时/保护回归8项通过；Task02六标签、同ID REST、画像字段、分页和外项目详情拒绝通过；Task05边界/异步/重启及真实同索引对照通过（4次调用、26日，48.862ms）。旧Task02/05本机验收工具已增加从私有初始化文件登录的兼容入口，不绕过鉴权。
- 真实浏览器5276登录、账号列表、成员列表、候选搜索，以及邀请生成/改角色/撤销通过；关闭后重开邀请弹窗无明文令牌。截图 `.data/task07-09-identity/browser-invites-revoked.png` 不含有效邀请令牌或密码。
- `.env.local` 校验不变，主5274与5280仍为sample；`src/`、`shared/`、`server/mock/` 相对基线零差异。无上游代码改动；`git diff --check`通过。未提交/推送，未推进任务10或执行任务16；上游既有18项基线失败未在本任务修复。

本机证据位于 `.data/task07-09-identity/`（live-acceptance.json、backend-tests.log、pnpm-verify.log、redocly.log、task02-regression.log及截图）。不包含密码、会话令牌或完整真实正文，不纳入提交。早期任务报告是当时状态快照，当前认证配置以本报告和README为准。
