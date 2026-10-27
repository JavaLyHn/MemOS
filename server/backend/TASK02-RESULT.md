# 任务 02：P0 记忆只读验收结果

交付范围：六标签记忆列表、详情、字段映射、项目范围、筛选分页、响应投影和真实链路对照。任务 03 的删除、任务 04 的日志，以及后续模块没有在本任务中实现。主前端 5274 继续使用 Mock；独立验收前端 5276 指向后端 5281。

## 实现与映射

Dashboard 新增 `server/backend/control.py`、`memory_models.py`、`memory_upstream.py`、`memories.py` 及对应测试；扩展 `settings.py`、`app.py` 与根 `openapi.json`。原任务 01 的未实现接口测试改用尚未实现的日志接口，原检查语义保持。没有改动 `src/`、`shared/`、`server/mock/`。

| 标签 | 真实来源 |
|---|---|
| text_mem | WorkingMemory、LongTermMemory、UserMemory、OuterMemory |
| pref_mem | PreferenceMemory |
| event_mem | EventMemory、Context、InsightMemory；不包含 DreamDiary |
| profile_mem | 有效绑定画像实例中的非空、未弃用、未删除字段 |
| skill_mem | SkillMemory |
| tool_mem | ToolSchemaMemory、ToolTrajectoryMemory |

五个图记忆标签使用上游 `/product/get_memory` 原生查询和 `/product/get_memory/{id}` 详情。上游增加可选 `status` 和 `event_memory_types` 参数；省略时保留原有行为。画像使用新增的 `/product/list_profile_memories`、`/product/get_profile_memory`，字段 ID 为稳定的实例 ID 加字段路径，支持下划线和中文，不通过语义召回代替全量列表。

上游修改涉及 `src/memos/api/profile.py`、`profile_memory_routes.py`、`product_models.py`、`handlers/memory_handler.py`、`routers/server_router.py`、相关测试与再生成的 `docs/openapi.json`。已有的 `universal_api.py` 兼容补丁属于环境准备，不能计入本任务实现。

## 查询与隔离口径

- 只返回 activated 状态；筛选之后计算 total，再按页返回，空页保留正确 total。图记忆沿用创建时间倒序、ID 倒序，画像按创建时间倒序、实例 ID 和路径稳定排序。
- `projectId` 通过配置与 SQLite 持久映射解析为 cube，旧数据库中未出现在当前配置的项目不获得访问权限。详情请求按规格没有 projectId，因此使用实例启动时固定的默认项目，不由其他列表请求改变。
- 同时支持搜索、创建时间、主体类型、主体 ID、知识库范围。日期按 UTC 自然日解释；带时区的时间戳转换为 UTC；日期结束值覆盖整天，时间戳结束值包含该时刻。非法参数返回 40000。
- 图记忆搜索遵循原生大小写敏感子串匹配；画像搜索使用 casefold。知识库筛选匹配已有图元数据 `knowledgebase_id`、`knowledge_base_id` 或数组 `knowledgebase_ids`；无关联画像不命中，不虚构知识库关系。
- 投影只输出接口字段，列表正文上限 500 字符加省略号、详情全文；不返回 embedding、sources、history 或整个 metadata。未知主体类型不冒充 user，只有可靠的遗留 user_id/agent_id 才补充主体。
- 画像 createTime 是实例 created_at，不把 updated_at 当创建时间。画像是字段视图，不是新的业务数据副本。
- 当前项目映射是本机操作员白名单，不是账号权限体系。`authEnabled=false`；完整项目生命周期和登录授权属于后续任务。不要将当前实例直接用作生产多用户服务。

## 真实验收证据

2026-10-26 使用真实 MemOS 8000、Dashboard 后端 5281、Neo4j 与画像存储验收。只调用一次真实 `/product/add` 抽取，新增独立测试标识，不删除已有记忆。未做额外 12—15 次付费抽取；真实分页用已有记录加新记录、每页 1 条验证，多页 25 条覆盖由单测完成。

| 检查 | 实测结果 |
|---|---|
| 唯一标记 | `Task02-43f4051aafd7` |
| 测试主体 | `task02-user-0d64856f96` |
| 列表发现的 memoryId | `e49e7bcc-279e-4264-ad3e-56dacffaeb10` |
| 同 ID REST 对照 | Dashboard 详情正文与上游原始 memory 逐字一致，类型为 UserMemory |
| 组合筛选 | 搜索 + 主体类型 + 主体 ID + 知识库 ID + 当天时间范围同时命中同一 ID |
| 知识库筛选数据 | 仅给本次新增测试记忆用既有更新接口添加测试知识库标签；不代表 P2 知识库功能已完成 |
| 真实分页 | total=2，第一页与第二页无重复，第三页空且 total 仍为 2 |
| 画像同 ID 对照 | 两个字段的列表、详情和上游同 ID 值相等，包含 basic.user_name 与 basic.城市 |
| 跨项目隔离 | B 项目列表不含 A 标记；另一个默认 B 的后端实例读取 A 的事实及画像 ID 均为 404/非零 code |
| 保留原数据 | 原环境验证记忆仍在事实列表中，未做清理或删除 |
| 浏览器 | 原前端源码在独立 5276 端口成功显示真实事实、画像字段和详情 |

画像字段 ID：

```text
profile_2894b0b247b74d9a861a63876a74836e_basic.user_name
profile_2894b0b247b74d9a861a63876a74836e_basic.城市
```

六标签均真实请求成功，事实 total=2、画像 total=2；偏好、事件、技能、工具目前真实 total=0。后四类通过真实空列表和合成数据的列表/详情/映射测试，不能称为真实有数据详情验证。

响应体积：真实事实列表 897 bytes，画像列表 848 bytes；空列表 90 bytes。10 行合成数据每行携带 1024 维 embedding 和大型 sources/history，上游投影后响应仅 1750 bytes，低于 200 KiB。上游响应有 32 MiB 读取上限，列表另有投影大小保护。

本机报告：`D:/MemOS/.local/task02-runtime-verification.json`；可重复只读脚本：`D:/MemOS/setup/verify_task02.py`，测试标识持久保存在 `.local/task02-seed.json`。这些是工作区环境文件，不随 Git 自动交付；仓库内的自动化回归测试不依赖它们或真实模型。

## 质量门

- Dashboard：`python -m pytest server/backend/tests -q`，110 passed；包含原任务 01 回归。
- 上游：画像、请求模型、原生六视图、读取范围、cloud routes、事件与图筛选相关测试，共 70 passed。
- Dashboard Ruff check 与 format --check 通过；上游本任务改动文件 Ruff check 通过。
- 独立审查未发现阻塞性缺陷。唯一日期溢出边界已修复：先复现 3 个失败用例，再修复并全量 110 项通过，极端 UTC 边界现在返回 400/40000。
- `pnpm verify`、Redocly、两仓库 diff 检查和最终运行验证结果见本文件末尾的最终检查记录。

失败用例覆盖上游 HTTP 错误、非 JSON、业务失败、畸形负载、超时、连接失败、错误项目/类型/ID、无项目配置、过大与压缩响应。错误保留非零 code，不用空列表冒充成功。

## 人工复验

打开 `http://127.0.0.1:5276/cn/memoryList`，事实标签应显示标记，点击“查看详情”可以看到上述真实 ID。用户记忆标签是画像字段视图，可看到 `basic.user_name` 与 `basic.城市`。删除按钮尚无本任务对应后端实现。

```powershell
$body = @{ projectId='issue3-project-a'; memoryDetailType='text_mem'; pageNum=1; pageSize=10; memSearchContent='Task02-43f4051aafd7' }
Invoke-RestMethod http://127.0.0.1:5281/api/dashboard/project/memory/list -Method Post -ContentType 'application/json' -Body ($body | ConvertTo-Json)
$detail = @{ memoryId='e49e7bcc-279e-4264-ad3e-56dacffaeb10'; memType='text_mem' }
Invoke-RestMethod http://127.0.0.1:5281/api/dashboard/project/memory/detail -Method Post -ContentType 'application/json' -Body ($detail | ConvertTo-Json)
```

## 对原实施计划的裁定

1. 事件统一走原生 get_memory，加可选事件类型过滤，保留旧默认；避免旧事件接口丢失组合筛选与主体元数据。代价是部署需同步上游补丁。
2. knowledgeBaseId 按真实元数据匹配，替代原计划的一律拒绝；成本是无关联数据不会命中，不意味着已实现知识库管理。
3. 未知主体不伪造为 user，保留可靠遗留字段回退；成本是部分旧记录主体可能为空。
4. 画像按 created_at，而非 updated_at；成本是编辑字段不会被伪装成新创建的记忆。
5. 明确采用本机白名单和固定默认项目，不提前做完整 P1；成本是当前不能提供多用户授权或通过页面切换活动项目。
6. 真实付费抽取缩减为一次，真实 2 条分页加合成 25 条分页；成本是四个空类型的有数据详情仍只有合成覆盖，已明确披露。
7. 将审查发现的日期溢出按参数错误契约修复；成本仅增加三个回归用例，不扩大功能范围。

本轮仅完成任务 02，代码尚未提交、推送或创建 PR；Issue #3 整体验收仍须后续任务完成。

## 最终检查记录

2026-10-26 03:23 UTC，在修复极端日期问题并重启后端后，重复运行真实验收脚本（不带 --seed）通过全部检查，未新增模型调用；任务 01 的 8 项真实 HTTP 检查全部通过。

- `pnpm verify`：typecheck、ESLint、Prettier、生产构建全部通过。构建存在原有大 chunk 提示，不影响结果，未为消除提示修改前端。
- `pnpm --package=@redocly/cli dlx redocly lint openapi.json`：0 errors、2 warnings（原有 info-license 和 localhost servers）。
- 两仓库 `git diff --check` 均通过；Dashboard 对基线 `03e10145a4dd8bc3e50b6e2a50ed788d64111945` 的 `src/ shared/ server/mock/` 差异为空。
- `.env.local` SHA256 前后均为 `05f6015a024755f20bf6a71233a0f1fd5bb13d2bf67f06e4c03a63d911dfe4d6`；5274 `/api/meta` 仍为 sample。
- 上游 docs/openapi.json 已由实际应用重新导出，新增 285 行，无删除；包含新只读画像路由、请求模型和可选过滤参数。
- 独立浏览器证据保存于 `D:/MemOS/.local/task02-memory-detail.png`。
