# Task05 — P1 用量交付结果

## 实现范围

`POST /api/dashboard/usage/query` 已交付。它通过与日志接口相同的 `AuditService` 做增量同步，再读取同一 SQLite `audit_calls` 逻辑记录；没有第二套 JSONL 统计器、逐次重新全读或人为生成业务次数。Task06 项目生命周期及账号鉴权没有提前实现。

主要代码：`usage_models.py`（参数和日期边界）、`usage_routes.py`（授权后同步及统一响应）、`AuditIndex.usage`（同索引聚合）、`ControlStore.authorized_cubes`（当前配置允许范围）。根 `openapi.json` 补齐原有 projectId 必填与 all/空串描述歧义，以及 summary/元数据和错误契约。前端保护目录不变。

## 固定统计口径

- 仅 `gateway` 来源；console 记忆页读取、删除及审计查询自身不计入用量。无法访问配置日志来源时明确503，不能假装0。
- `addMessage` / `searchMemory` / `rerank` 提供 `calls` 和 `totalTokens`；`chat` / `extractMemory` 提供请求、响应、总 token。所有五种分组每天存在，空日为0；不因为分组对象存在而虚构一次调用。未知事件不凑入已知事件。
- `summary.totalCalls` = `addMessage.calls + searchMemory.calls`，与当前前端总请求卡片口径一致，不声称等于所有网关事件次数。`summary.totalTokens` 是五个已知事件的 token 之和；每条缺失 token 按0，不按文本长度推算，也不是账单。
- SUCCESS / FAILURE / PENDING / UNKNOWN 都是已观察到的调用，各逻辑行计一次。异步请求、重复终态按 Task04 的来源+cube+callId 合并；终态到达会更新原调用 token，不增加次数。日期优先请求时间，终态先到且缺请求时暂用终态时间，后续请求到达可纠正归属日期。
- `projectId` 省略、null、空白或 `all`：只遍历当前进程配置 allowlist；具体项目不在范围返回404。数据库残留但本次配置已移除的项目不进入全项目统计。无配置范围返回503。先校验范围，再扫描审计文件。
- 以上是当前本地操作员配置授权边界；`authEnabled=false`，尚未交付 P1 账号会话/成员角色，不能称生产多用户鉴权完成。
- 日界线与前端一致：北京时间固定 UTC+8，响应 `timezone=Asia/Shanghai`。`startDate/endDate` 仅接受 YYYY-MM-DD（空白/null等同未传），不接受 timestamp；默认当月1日至今天，最多366天，首尾日期包含。实际索引条件为 `[开始日00:00, 结束日次日00:00)`。每个请求验证时固定默认日期，跨月不会重新取今天导致500。无合法时间的历史行仍在日志中，但不归入任何日用量。UTC+8 为当前 UI 的固定时区口径，不处理历史上海夏令时。
- `includeDailyDetails=false` 返回 `dailyStats=[]` 及完全相同的 `summary`，避免静默忽略。非空 `apiKeyId` 目前明确400，理由是审计没有可信密钥 ID；不能忽略此筛选返回更宽范围，也不取完整密钥作为身份。

## 验证证据

行为测试包含：UTC+8 两侧微秒边界、失败/pending、空日、历史无时间、未知事件、来源隔离、真实/缺失 token、异步更新只计一次、项目all与移除配置残留、授权先于摄取、apiKeyId不支持、366天/闰日、无效日期/上界溢出、默认当月/跨月请求一致性。首轮18项RED后实现GREEN；跨月500问题另补RED再修复。

- Task05 专项：25项通过。
- 全后端187项通过（9.45秒）；Ruff检查通过；Task01真实运行信息/故障/Mock保护回归全部通过。
- `D:/MemOS/setup/verify_task05.py`：独立真实HTTP夹具验证边界、异步、重启与配置撤权，通过；2个逻辑调用、16个真实夹具token。
- 5281真实HTTP与同一生产审计索引逐日对照通过：当前项目4次add/search、26个自然日，50.129ms（此为已持久索引上的当次查询，不冒称10k冷启动性能）。无新模型调用，无真实记忆写入或删除。
- Task01 未实现接口负例从已经实现的 usage/query 改为尚未实现的 project/create；其余既有验证保留。

验收仅覆盖 Task05 以及必要回归。主5274保持Mock，独立5276可查看真实用量。未执行Task16停止Mock后的全模块验收，原有上游基线失败仍按Task03报告说明。

## 用户验证

打开 `http://127.0.0.1:5276/cn/usage`，选择 `issue3-project-a`，查看7/14/30天次数与每日明细。接口示例：

```json
{"projectId":"issue3-project-a","startDate":"2026-10-01","endDate":"2026-10-26","includeDailyDetails":true}
```

向 `http://127.0.0.1:5281/api/dashboard/usage/query` 发送 POST；成功统一信封 `code=0`，`data.dailyStats` 是逐日数据，`data.summary` 是区间汇总。日期按实际验证日期调整。

最终只读审查提出的日期契约差异已修复：根日期schema使用null/纯空白/严格日期三分支，与实现一致；非空日期两侧空白明确400。新增带FormatChecker的根请求契约测试和4个HTTP参数回归，先RED后GREEN。主控独立随机oracle、原始JSONL对照及前端最终验收另由主控记录。


## 主控最终独立验收

- 子 agent 实现和只读审查均继承主 agent 的模型与思考强度，本任务未使用 Astra；主控另行独立验收。
- 主控重跑后端全套：187 passed（9.07秒）；Ruff check / format 全部通过（31个Python文件）。日期请求schema差异已由实现子agent按RED/GREEN修复，限定只读复核25项再次通过，无遗留审查项。
- 独立240行随机夹具，含多时区、不同租户、失败状态、未知事件和真实/缺失Token，以另一份Python日历算法逐日核对：7天、70次调用、796Token，全部一致。
- 只读原始2份 `calls-*.jsonl` 独立计数，与真实接口逐日对照：本月26天、4次add/search调用，全部归属北京时间2026-10-26。这里的原始行计数仅用于当前没有callId的真实记录对照；异步去重另由带关联ID的隔离夹具验证，不冒称生产异步投递已验收。
- 独立真实前端 http://127.0.0.1:5276/cn/usage 的近7/14/30天、每日明细和零日期展示均通过，显示4次检索、0次写入。控制台记忆操作日志不膨胀此处工具用量。
- `pnpm verify`：TypeScript、ESLint、Prettier及生产构建通过，保留既有chunk大小提示。Redocly：0errors、2条既有警告；未新增HTTP操作（仍60路径、63操作）。
- `src/`、`shared/`、`server/mock/` 对基线零差异；`.env.local` 哈希一致，主5274仍为sample。git diff --check通过。
- 独立验收输出位于 `.data/task05-maincheck/`，实现者HTTP输出位于 `.data/task05-usage/acceptance.json`。这些文件只保存检查结果与汇总，不存密钥或完整真实正文；不纳入提交。

仍采用既定边界：固定UTC+8日历、不处理历史DST；全项目仅当前本地操作员配置allowlist，完整账号/成员鉴权属于后续任务；非空apiKeyId明确不支持；Token按已记录值统计，缺失为0，不能当作模型账单。断电、多机、生产异步网关投递及Task06以后功能不属于本次验收。没有调用付费模型，没有写删真实记忆，没有推进任务06或执行任务16全模块验收。
