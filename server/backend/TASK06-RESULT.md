# Task06 — P1 项目工作区交付结果

## 交付范围

已实现真实项目列表、创建、更新、选中、停用、可恢复归档及恢复，以及服务重启后的持久化。数据写入 `D:/MemOS/dashboard/.data/control.db`，不再使用固定项目字典冒充完整项目管理。本任务由主 agent 实施和复核，没有新增子 agent；未推进任务07，也未提交或推送代码。

接口：`GET project/dict`；`POST project/list`、`project/create`、`project/update`、`project/delete/{id}`、`project/restore/{id}`、`project/revoke/{id}`，共同前缀 `/api/dashboard/`。列表返回 `records/total`，统一信封 `code/data/message`。根 `openapi.json` 记录可写字段、分页上限、状态语义和错误响应；归档/恢复沿用现有规格操作，未增加额外路径。

## 设计和实现

- `control.py` 事务迁移旧四列表，保留原项目 ID、名称、创建时间及上游映射。种子启动插入不覆盖已修改名称、停用或归档状态；配置映射冲突拒绝启动。新建项目分配不可变 UUID ID，上游 namespace 与该 ID 对应，客户端不能指定其他租户、所有者或归档元数据。
- 种子访问范围来自本进程配置；本地操作员通过接口创建的项目有持久管理标记，重启仍可访问。配置移除的旧种子不因数据库残留而重新获得访问范围。
- `project_models.py` 限制可写字段和大小，严格分页，拒绝 null 更新与空更新；名称采用 NFKC/casefold 唯一键。事务保护并发同名创建、部分更新回滚和状态变化。
- `project_context.py` 使用30天 HttpOnly、SameSite=Lax cookie 保存不透明偏好标识，数据库仅存 SHA256 摘要；HTTPS 下使用 Secure。两个浏览器上下文独立选择，同一上下文重启后保留。该 cookie 是项目偏好，不是登录凭证。
- `status=ENABLED` 仅表示本上下文的当前活跃项目；非当前项目也可能 `status=DISABLED, disabled=false`，不能与真正停用混淆。对停用项目发送 ENABLED 只重新启用，再次发送才选中；归档恢复不自动切换，且保留原停用状态。
- 停用/归档后移出活跃字典，记忆、日志、用量显式项目接口拒绝读取；只对选中目标的上下文回退。记忆详情、日志详情及对应控制台审计关联改用当前上下文，不再固定配置默认项目。无活跃项目时字典为空，详情明确不可用。
- 归档为控制面软删除，revoke 是兼容别名，不删除 MemOS、图、向量或记忆正文。新项目 namespace 通过真实上游六种读取视图验证为空；未调用属于另一套 owner 注册协议的 `/create_cube`，也未生成假记忆。
- `projects.py` 复用写操作 Origin 检查，数据库故障统一503，非法参数400、重名/归档更新409、未知或不可访问项目404，不返回假成功。

主要文件：`control.py`、`project_models.py`、`project_context.py`、`projects.py`、`app.py`、`memories.py`、`audit_routes.py`、`audit_writer.py`、`tests/test_projects.py`。测试 conftest 隔离工作目录，防止默认配置污染真实 `.data`。

## 已执行验证

- 全后端 **204 passed，13.97秒**，其中17项项目专项测试；包含旧库迁移、重启、独立上下文、停用/归档门禁、空项目、并发重名、回滚、Origin、字段/分页及实际响应对根 OpenAPI 的结构校验。
- Ruff check 和 format check：36个 Python 文件通过。
- `pnpm verify`：TypeScript、ESLint、Prettier及生产构建通过；保留原有大 chunk 提示。
- `pnpm --package=@redocly/cli dlx redocly lint openapi.json`：0错误，2条既有警告（license、localhost server）。
- `D:/MemOS/setup/verify_task06.py`：同一个临时 SQLite 库上三次真实 HTTP 服务器实例验证完整生命周期；这两次实例重建不冒称操作系统进程重启。真实5281服务另做 **三次操作系统进程重启**，逐次验证当前选择、停用状态、归档状态持久化，且旧项目与原标识记忆仍存在。
- 实际验收项目 `proj_d819620bb02441958981be2ade083248` 最终保留为可恢复归档。新 namespace 六视图为空，原项目 A 的标识记忆 `61ca5bdd-65bc-4c5d-9fcc-115e7cea396c` 全程保持可读。
- 修正验收脚本必须存在上次测试残留的错误假设。Windows 启动器输出改用普通临时文件，避免长驻后端继承管道导致等待 EOF 超时；保留启动器退出码和健康检查。重启改用已校验所有权的 Stop/Start，停止 Python 父子进程树。单独重跑修正后的 Restart-Backend.ps1 通过，进程替换完成，用时4.72秒。
- Task01真实健康/连接失败/超时/Mock保护8项回归通过；Task02六标签、同ID REST、分页、画像及外项目详情拒绝回归通过；Task05隔离边界/异步/重启及真实同索引逐日对照通过（当前4次调用、26天，查询75.202ms）。本次未调用付费模型，未写删真实记忆。
- 独立真实前端5276完成新建、编辑、设为当前、停用、启用、归档、恢复。浏览器测试项目 `Task06-ui-20261026-edited` / `proj_bdf912eab65347ee87eaa0c94ad0f01b` 恢复为正常，当前选择回到 `issue3-project-a`。
- 主5274及Mock5280仍为sample，`.env.local` 校验一致；`src/`、`shared/`、`server/mock/` 相对基线零差异。无上游代码改动。

本机验收记录：`.data/task06-projects/acceptance.json`、`pnpm-verify.log`、`redocly.log` 和 `browser-projects-restored.png`；这些本地证据不包含密钥或完整记忆正文，不纳入提交。Task01与Task02既有验收记录、Task05 acceptance 已刷新。

## 用户验证与明确边界

打开 http://127.0.0.1:5276/cn/projects 操作测试项目；5274仍展示原Mock。可新建、编辑、切换、停用、启用、归档和恢复，重启后再次读取列表核对。直接接口使用 project/list 的 `records`，不能用其他模块的 `list/logs` 键。

既有前端在归档当前项目时曾显示成功提示且侧栏已回退，但表格仍保留旧状态；重新载入后显示“已归档”，恢复操作立即显示“正常”。后端独立读取及重启证据均正确。遵守本任务 `src/` 零变更约束，未修改此表格缓存行为，也不宣称无刷新的页面状态同步已完全通过。创建表单中“名称同时作为ID”的既有提示也与服务端生成ID不一致，真实返回的ID应以接口为准。

`authEnabled=false`，`role=owner` 是本机受信操作员能力，账号、成员、邀请与登录会话属于任务07。前端归档提示中“成员/API Key立即失效、恢复原样可用”超出本任务：目前仅控制台数据接口受项目状态约束，网关密钥配置/停用联动尚未交付，不能据此声称网关调用已被阻断。新建项目也不会自动创建网关密钥。

未执行任务16停Mock后的全模块验收。上游既有18项基线失败仍见TASK03报告，不宣称其已修复。
