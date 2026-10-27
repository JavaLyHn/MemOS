# 分层授权约定交付

2026-10-27。用户明确选择平台管理员与项目角色分层授权。本次将既有权限规则补齐为可审阅的接口规格与权限矩阵，没有修改运行时策略或前端。

- AUTHORIZATION.md 逐接口定义当前账号、全站账号管理、项目成员、候选搜索、邀请与退出权限；注明最后管理员/owner、项目隔离和令牌接受边界。
- openapi.json 修正原笼统管理员说明，为当前账号及全部 /admin/* 操作补充 description 和 x-authorization；不改 URL、请求/响应形状或角色校验。
- README、Task16报告和第三节审查记录增加已选方案说明。历史审查记录保留，不声称上游维护者已批准解释。
- test_authorization_policy.py 新增6项：四种非平台管理员身份（viewer/editor/owner/外项目账号）的全套管理接口权限、匿名拒绝、规格元数据一致性。

验证：权限、账号、成员、邀请共23项通过（18.67秒）；Ruff check/format通过；Redocly0错误、6条已有警告；git diff --check通过。src/shared/server/mock/.env.local相对03e10145仍为空diff。没有重跑此前已通过的全量测试，没有操作真实账号或重启服务。

日志：.data/authorization-policy-tests.log、.data/authorization-redocly.log。规格测试曾先因缺少权限元数据失败，再补齐通过；新增测试夹具的邀请有效期按现有契约使用24h，不扩展接口支持单位。

交付说明：Issue #3 的管理员要求在本实现中解释为平台操作需要平台管理员，项目管理需要目标项目owner；成员可读本项目成员列表并退出自己。路径中的 /admin/ 不是全局平台管理员门禁。
