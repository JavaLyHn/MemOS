# 分层授权约定

2026-10-27：用户选择分层授权方案。本文解释 Issue #3 的管理员要求：平台操作由平台管理员执行，项目操作由项目角色授权；URL 中的 /admin/ 前缀不意味着全部操作都要求平台管理员。此解释应随交付说明提交，未声称已获得上游维护者确认。

## 接口权限矩阵

以下接口均要求有效登录。表中“成员”指目标项目的 viewer/editor/owner，不包含其他项目的成员。平台管理员可覆盖项目角色检查，但个人空间、项目状态、最后 owner 等业务约束仍生效。

| 接口 | 最低权限 | 范围/约束 |
|---|---|---|
| GET /api/auth/me | 已登录 | 只返回当前会话账号 |
| GET /admin/accounts | 平台管理员 | 全站账号列表 |
| POST /admin/accounts/{id} | 平台管理员 | 更新账号，保护最后有效管理员及 owner |
| DELETE /admin/accounts/{id} | 平台管理员 | 删除账号，保护最后有效管理员及 owner |
| GET /admin/tenants/{tenantId}/members | 项目 viewer | 仅目标团队项目 |
| GET /admin/tenants/{tenantId}/member-candidates | 项目 owner | 候选账号搜索，不授予全站账号管理权限 |
| POST /admin/tenants/{tenantId}/members | 项目 owner | 添加或修改成员；项目需可用，保护最后有效 owner |
| POST /admin/tenants/{tenantId}/members/{accountId}/remove | 项目 owner | 仅目标项目；保护最后有效 owner |
| POST /admin/tenants/{tenantId}/members/leave | 本项目成员 | 仅退出自己；保护最后有效 owner |
| GET /admin/tenants/{tenantId}/invites | 项目 owner | 仅目标团队项目 |
| POST /admin/tenants/{tenantId}/invites | 项目 owner | 目标项目需可用 |
| POST /admin/tenants/{tenantId}/invites/{inviteId}/role | 项目 owner | 邀请必须属于该项目 |
| POST /admin/tenants/{tenantId}/invites/{inviteId}/revoke | 项目 owner | 邀请必须属于该项目 |

## 授权边界

- 匿名、过期会话、禁用或已删除账号访问受保护接口返回401。
- 可见项目中角色不足返回403；不可访问的项目或不属于该项目的资源返回404，避免泄露资源存在性。
- project owner 不是 platform_admin，不能列出、更新或删除全站账号，也不能管理其他项目。
- 邀请接受走独立的令牌与表单校验流程；可以使用有效邀请加入项目，不要求接受者已有该项目权限。撤销、过期、重复使用不授予权限。
- 成员离开和管理操作仍受事务内最后有效 owner 保护；账号管理受最后有效平台管理员保护。
- 浏览器写请求保留 Origin/CSRF 校验；本约定没有放宽来源或会话保护。
- auth_enabled=false 是已有本地受信操作员模式，不是生产角色策略；正式验收使用默认开启的鉴权。

## 接口规格与验证

openapi.json 在 /api/auth/me 和每条 /admin/* 操作的 description 与 x-authorization 中明确上述要求。扩展字段是权限文档元数据，运行时仍由既有会话、actor_for、ControlStore 与 workspace 校验执行，不宣称 OpenAPI 本身能执行鉴权。

本次仅补齐规格、文档和回归测试，不修改运行时权限逻辑、前端、上游或真实账号。test_authorization_policy.py 覆盖 viewer/editor/非平台管理员 owner/外项目账号的全套管理操作、跨项目拒绝、匿名拒绝和规格矩阵一致性。已有账号、成员、邀请测试继续覆盖最后管理员/owner、禁用、过期和撤销。
