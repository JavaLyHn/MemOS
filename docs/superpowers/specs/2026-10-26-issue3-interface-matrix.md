# Issue 3：接口实施矩阵（逐项交付）

来源：当前 openapi.json；逐 method + path 统计。已交付任务 01 的 GET /api/meta，任务 02 的 memory/list、memory/detail 和记忆页最小 project/dict 映射，任务 03 的 memory/delete、restore、retry、operation。详见 server/backend/TASK01-RESULT.md、TASK02-RESULT.md、TASK03-RESULT.md。任务 04 的 log/list、log/detail 已交付，支持来源筛选、JSONL 增量索引和异步关联，详见 server/backend/TASK04-RESULT.md。任务05用量、任务06项目生命周期已交付，详见 TASK05-RESULT.md、TASK06-RESULT.md；任务07账号、任务08成员、任务09邀请已交付，另见 TASK07-RESULT.md、TASK08-RESULT.md、TASK09-RESULT.md。

任务12 Prompt与任务13图谱/模型已交付，见TASK12-RESULT.md、TASK13-RESULT.md；知识库任务10/11按用户要求冻结现状，不计为本轮完整验收。

共 63 条路径，69 个 HTTP 操作（任务03补充恢复/重试/回执，任务07—09补充登录、退出和邀请落地HTML各GET/POST）。P3密钥与模板已交付（模板前端仍占位），明确豁免模块仍需正确返回约定结构。

| 方法 | 路径 | 优先级 | 必填 JSON 字段（非完整参数清单） | 200 响应定义 |
|---|---|---|---|---|
| GET | /api/dashboard/project/dict | P1（任务06已验收） | 见 schema / query / path | ProjectDict |
| POST | /api/dashboard/project/list | P1（任务06已验收） | 见 schema / query / path | ProjectRecords |
| POST | /api/dashboard/project/create | P1（任务06已验收） | name, description | Project |
| POST | /api/dashboard/project/update | P1（任务06已验收） | id + 至少一个可写字段 | Project |
| POST | /api/dashboard/project/revoke/{id} | P1（任务06已验收） | 见 schema / query / path | Ok |
| POST | /api/dashboard/keys/list | 已实现（task14） | projectId | ApiKeyRecords |
| POST | /api/dashboard/keys/create | 已实现（task14） | projectId, keyName | ApiKey |
| POST | /api/dashboard/keys/revoke/{id} | 已实现（task14） | 见 schema / query / path | Ok |
| POST | /api/dashboard/keys/copy | 已实现（task14） | apiKeyId | StringData |
| POST | /api/dashboard/log/list | P0（任务04已验收） | projectId | LogList |
| POST | /api/dashboard/log/detail | P0（任务04已验收） | logId | LogDetail |
| POST | /api/dashboard/project/memory/list | P0 | projectId, memoryDetailType | MemoryList |
| POST | /api/dashboard/project/memory/detail | P0 | memoryId, memType | Memory |
| POST | /api/dashboard/project/memory/delete | P0 | projectId, memory_ids, memType | MemoryOperation（保留 deleted） |
| POST | /api/dashboard/project/memory/restore | P0 | projectId, memory_ids, memType | MemoryOperation |
| POST | /api/dashboard/project/memory/retry | P0 | projectId, operationId | MemoryOperation |
| GET | /api/dashboard/project/memory/operation | P0 | query: projectId, operationId | MemoryOperation |
| POST | /api/dashboard/knowledgebase/list | P2（用户冻结现状） | 见 schema / query / path | KnowledgeBaseRecords |
| POST | /api/dashboard/knowledgebase/create | P2（用户冻结现状） | knowledgebaseName | KnowledgeBase |
| POST | /api/dashboard/knowledgebase/update | P2（用户冻结现状） | id | KnowledgeBase |
| POST | /api/dashboard/knowledgebase/detail | P2（用户冻结现状） | knowledgeBaseId | KnowledgeBase |
| POST | /api/dashboard/knowledgebase/file/list | P2（用户冻结现状） | knowledgeBaseId | UntypedRecords |
| POST | /api/dashboard/knowledgebase/memory/list | P2（用户冻结现状） | knowledgeBaseId | MemoryRecords |
| POST | /api/dashboard/knowledgebase/project/associate | P2（用户冻结现状） | projectId, knowledgeBaseIds | Ok |
| POST | /api/dashboard/knowledgebase/project/remove | P2（用户冻结现状） | projectId, knowledgeBaseId | Ok |
| POST | /api/dashboard/profileTemplate/list | P3（任务15已实现，前端占位） | projectId | ProfileTemplateList |
| GET | /api/dashboard/profileTemplate/detail | P3（任务15已实现，前端占位） | 见 schema / query / path | ProfileTemplate |
| POST | /api/dashboard/profileTemplate/create | P3（任务15已实现，前端占位） | 见 schema / query / path | Ok |
| POST | /api/dashboard/profileTemplate/update | P3（任务15已实现，前端占位） | 见 schema / query / path | Ok |
| POST | /api/dashboard/profileTemplate/delete | P3（任务15已实现，前端占位） | projectId, templateId | Ok |
| POST | /api/dashboard/prompt-config/detail | P2（任务12已验收） | 见 schema / query / path | PromptConfig |
| POST | /api/dashboard/prompt-config/save | P2（任务12已验收） | 见 schema / query / path | Ok |
| POST | /api/dashboard/prompt-config/generate | P2（任务12已验收） | 见 schema / query / path | Prompt |
| POST | /api/dashboard/prompt-config/reset-default | P2（任务12已验收） | 见 schema / query / path | Prompt |
| POST | /api/dashboard/prompt-config/debug/extract | P2（任务12已验收） | 见 schema / query / path | ExtractDebug |
| POST | /api/dashboard/usage/query | P1（任务05已验收） | 无（projectId可选，省略仅查询授权范围） | UsageQuery |
| POST | /api/dashboard/skill/skillMD | 固定成功返回（已实现） | oss_url | StringData |
| GET | /api/user/quota/summary | 固定成功返回（已实现） | 见 schema / query / path | QuotaSummary |
| POST | /api/user/subscription/details | 固定成功返回（已实现） | 见 schema / query / path | SubscriptionDetails |
| GET | /api/meta | P0 | 见 schema / query / path | Meta |
| GET | /api/auth/me | P1（任务07已验收） | 见 schema / query / path | Account |
| POST | /api/dashboard/project/delete/{id} | P1（任务06已验收） | 见 schema / query / path | ProjectArchive |
| POST | /api/dashboard/project/restore/{id} | P1（任务06已验收） | 见 schema / query / path | Project |
| POST | /api/dashboard/keys/rename/{id} | 已实现（task14） | keyName | ApiKey |
| POST | /api/dashboard/knowledgebase/delete | P2（用户冻结现状） | projectId, knowledgeBaseId | KnowledgeBaseDelete |
| POST | /api/dashboard/knowledgebase/file/add | P2（用户冻结现状） | projectId, knowledgeBaseId, file | KnowledgeFileRecords |
| POST | /api/dashboard/knowledgebase/file/delete | P2（用户冻结现状） | projectId, fileIds | KnowledgeFileDelete |
| GET | /api/dashboard/knowledgebase/file/download | P2（用户冻结现状） | 见 schema / query / path | FileDownload |
| GET | /api/dashboard/graph/memories | P2（任务13已验收） | 见 schema / query / path | GraphMemoryGraph |
| GET | /api/dashboard/graph/memory | P2（任务13已验收） | 见 schema / query / path | GraphMemory |
| GET | /api/dashboard/models | P2（任务13已验收） | 见 schema / query / path | ModelRecords |
| GET | /admin/accounts | P1（任务07已验收） | 见 schema / query / path | AdminAccountRecords |
| POST | /admin/accounts/{id} | P1（任务07已验收） | 见 schema / query / path | AdminAccount |
| DELETE | /admin/accounts/{id} | P1（任务07已验收） | 见 schema / query / path | Ok |
| GET | /admin/tenants/{tenantId}/members | P1（任务08已验收） | 见 schema / query / path | ProjectMemberRecords |
| POST | /admin/tenants/{tenantId}/members | P1（任务08已验收） | role | MemberSet |
| POST | /admin/tenants/{tenantId}/members/{accountId}/remove | P1（任务08已验收） | 见 schema / query / path | Ok |
| POST | /admin/tenants/{tenantId}/members/leave | P1（任务08已验收） | 见 schema / query / path | Ok |
| GET | /admin/tenants/{tenantId}/member-candidates | P1（任务08已验收） | 见 schema / query / path | MemberCandidateRecords |
| GET | /admin/tenants/{tenantId}/invites | P1（任务09已验收） | 见 schema / query / path | ProjectInviteRecords |
| POST | /admin/tenants/{tenantId}/invites | P1（任务09已验收） | role | CreatedInvite |
| POST | /admin/tenants/{tenantId}/invites/{inviteId}/revoke | P1（任务09已验收） | 见 schema / query / path | Ok |
| POST | /admin/tenants/{tenantId}/invites/{inviteId}/role | P1（任务09已验收） | role | InviteRole |

后端HTML入口：GET/POST `/__login`（任务07）、GET/POST `/__logout`（任务07）、GET/POST `/__login/invite/{token}`（任务09）。GET成功返回HTML，POST成功返回303；JSON错误仍为统一信封。业务接口默认要求 `memos_session`，权限不足401/403，事务约束冲突409，邀请过期410。
