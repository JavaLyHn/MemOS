# 浏览器无请求体写请求兼容修复

2026-10-27。用户反馈memos-admin撤销密钥提示无权限。

## 根因

真实auth/me确认memos-admin的platformAdmin=true。前端keys.revoke使用无body POST，不带Content-Type；浏览器附带Origin。原会话中间件把所有带Origin的非JSON写请求统一403，导致路由尚未执行就显示无权限。相同问题影响无body DELETE账号、POST项目归档/恢复等前端调用。

修复前已用同一管理员会话复现：带合法Origin且无body请求未知key，403；同路径改发JSON空对象则404，证明角色检查不是拒绝来源。没有撤销用户密钥。

## 修复

先检查Origin白名单，再允许application/json或真正空的无Content-Type请求。对后者实际读取首个ASGI请求消息验证，不只相信Content-Length；含正文、非空分块、非JSON媒体类型仍拒绝。空请求消息原样重放，下游需要body的接口仍按原契约返回400。所有原有角色检查保留。

## 验证

新增3条回归：管理员真实请求形状撤销测试密钥；跨源/无类型正文/伪造Content-Length与viewer写拒绝；无body账号删除及项目归档恢复。新用例先失败后修复。

主站5274实测本轮临时测试密钥，合法Origin且无请求体撤销200/code0；列表和配置均移除本轮key，最终tenants.conf与测试前逐字节一致。没有删除用户已有密钥，也未重启网关使临时key生效。

后端已重启，全量后端310 passed（103.51秒），Ruff与本轮3文件格式检查通过；src/shared/server/mock/.env.local对基线无差异。日志见.data/bodyless-tests.log，真实证据见.data/bodyless-live.json。未提交代码。

使用：刷新原密钥页后重新撤销目标密钥。撤销落盘后仍需重启网关，才让运行中的旧凭据失效。
