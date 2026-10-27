# Issue 3 第三节独立复核

> 后续结论（2026-10-27）：用户已明确选择分层授权，原文提到的权限解释歧义已在本实现范围内澄清。具体规则见 AUTHORIZATION.md 与 OpenAPI 的逐接口权限元数据；下文保留作原始审查记录。不声称上游维护者已经确认这一解释。

复核日期：2026-10-27。读取最新 GitHub Issue 正文，检查当前工作区代码，执行真实只读 HTTP 与隔离测试；本轮没有修改业务代码、权限策略或前端。

结论：响应体积、字段映射、记忆状态/恢复、历史日志兼容均有通过证据。鉴权采用平台管理员与项目角色两层授权；如果严格解释 Issue 的“/admin/* 需要管理员身份”为全部路由仅平台管理员可访问，则当前实现存在偏差，不能宣称该节逐字全部满足。

## 1. 响应体积

memories.project_node 使用 MemoryItem 白名单投影；不返回 metadata.embedding、sources、history。列表正文最多 500 字后加省略号，详情独立保留全文。列表还有 200 KiB 数据体积保护。

真实 issue3-project-a 的 text_mem 一页 10 条，总数 10，完整 HTTP JSON 响应 3688 字节；profile_mem 一页 4 条，1555 字节；另外四类为空，各 90 字节。均小于验收的 200 KB。合成测试还包含 1024 维向量与大 sources/history，验证没有透传。

## 2. 字段映射

列表和详情共同使用 memories.py 的 project_node：id→memoryId、memory→memoryContent、created_at→createTime。画像行的扁平字段和普通记忆 metadata 在这一处归一；六标签映射在 memory_models.TAB_TYPES；展示时间由 timefmt 统一转换。图谱有独立的 GraphNode 投影，因为其契约就是另一种形状。

## 3. 时间与状态

记忆列表/详情使用 createTime，真实结果为 YYYY-MM-DD HH:MM:SS（固定 UTC+8），存储/查询机器时间不被展示转换覆盖。列表上游查询限定 activated，投影再次检查状态；图谱同样只返回激活节点。删除/恢复具备幂等回执、同步确认及失败重试，普通记忆检查图向量，画像字段走字段状态转换。

已有真实合成画像字段生命周期证据为 8→7→8、删除时全文404、恢复后同 ID/正文一致，见 .data/profile-graph-repair/live.json。本轮没有再次改变真实数据。

Issue 对时间字段的概括与其接口定义有例外：图谱为 createdAt，账号/成员为 created_at，邀请为 createdAt/expiresAt 等。当前按权威 spec 保留这些字段，不能把它们全部改名为 createTime。原始日志无时间戳时返回空串，不伪造时间。

## 4. 历史 JSONL

audit_normalize 集中做默认值与兼容：缺 input/output 时输出合法 JSON 字符串 null；缺耗时为 null、缺 token 为0、缺时间为空串、无成功/失败证据时为 UNKNOWN。缺失/无效租户的记录隔离，不猜测归属；坏 JSON 记录拒收但不使整页失败。隔离与拒收不是“所有旧记录都一定显示”，而是在不串租户前提下兼容可归属记录。

## 5. 账号与鉴权

/api/auth/me 来自真实持久会话，匿名401；/admin/accounts 列表/更新/删除均要求 platform_admin。禁用、删除、过期会话失效。账号、成员、邀请均落 SQLite 控制面。

但 /admin/tenants/{tenantId}/members 允许该项目 viewer 读取；成员变更和邀请管理要求项目 owner，leave 允许当前成员退出。隔离测试实测非平台管理员 viewer：成员列表200，账号列表403。这是有项目边界的角色策略，不是匿名开放，但与“全部 /admin/* 都仅平台管理员”不一致。需要明确采用哪种解释后再修改；本轮不擅自改变权限。

密钥签发写配置、重启网关生效的既有真实验收记录：.data/task14-keys/task14-live.json 共20项，complete.passed=true。本轮之前刚通过现有有效项目密钥完成5次真实MCP写入、形成6条记忆，同ID REST一致，见.data/graph-demo/result.json；不能把“既有密钥当前可用”冒充“本轮新建密钥再次验收”。

## 本轮验证

- 日志、时间、账号、成员、邀请、生命周期及密钥相关测试：95 passed，33.50秒。
- 记忆列表、详情、图谱与画像图谱相关测试：63 passed，18.62秒。
- 共158项通过；这是本轮针对性回归，不是声称重跑全量318项。
- 真实只读证据：.data/implementation-notes/live.json。
- 日志：.data/implementation-notes-tests.log、.data/implementation-notes-memory-tests.log。
- src/ 相对基线03e10145仍为空diff。

列表与图谱的中文类型命名不一致是已记录的前端限制，属于其他展示问题，不应通过更改上游真实类型掩盖，也不能因本节的后端检查通过就宣称它已解决。
