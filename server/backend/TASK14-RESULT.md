# TASK14-RESULT：P3接口密钥（2026-10-27最终复验）

> 后续增强：网关已支持配置变化检测与自动重载，当前创建/撤销无需重启，见 GATEWAY-RELOAD-RESULT.md。下文重启生效记录是升级前的真实历史验收；重演脚本已更新为无需重启网关并检查PID不变。

任务14已修复独立复核发现的5项问题并通过本轮专项验收。仅主agent执行，无子agent、无Git提交；知识库、前端、Mock及任务15/16保持原范围。

## 实现与关闭问题

| 项目 | 最终行为 |
|---|---|
| SQLite与网关文件一致性 | 所有配置发布和网关加载共用跨进程advisory lock；事务提交前设置pending。提交失败立即按已提交数据库恢复文件，补偿失败保留pending并返回明确503；网关拒绝加载pending配置。启动或后续成功变更可按数据库自愈。不是跨介质原子事务。 |
| 凭据错误脱敏 | env/file解析错误使用固定无凭据消息，屏蔽原异常上下文；冲突仅带掩码。兼容原有缺省/null cube回退user语义。 |
| 安全清理 | 每轮创建新隔离项目，只处理本轮获得的key ID；finally撤销本轮key并归档本轮项目。不再枚举或撤销issue3-project-a的现有密钥。 |
| 自动验收门禁 | 所有状态码、真实检索、审计租户、重启PID、配置字节均为必须通过的require；失败非0，记录明确failed/complete状态。每轮run_id唯一，禁止覆盖旧证据；序列化扫描通过后才落盘和输出。 |
| 本机直连 | 所有探针/驱动HTTP客户端trust_env=False，避免Windows系统代理干扰。恶意token模式以401为成功预期。 |

5条keys路由契约不变：owner/platform_admin授权，完整密钥下发；分页records/total；copy.data为完整字符串；改名不改网关字节；撤销行保留可审计。明文存储依原契约保留，没有宣称KMS或一次可见。

发布协调路径为tenants.conf.lock与tenants.conf.pending，Dashboard和网关必须使用同一个配置路径与共享协调目录。锁文件首次创建需要目录写权限。该协议覆盖并发读取、提交失败、补偿失败及进程崩溃恢复，不承诺断电跨文件系统原子性。已运行网关继续使用启动快照，签发/撤销仍需重启生效。

Restart-Gateway.ps1在停止已有网关前检查已知pending状态；正式加载时仍受发布锁和pending校验保护。敏感临时文件使用唯一名称、写入刷新、原子替换、finally清理；锁、pending及崩溃残留临时文件均已加入上游ignore。

## 新的真实验收

当前task14-live.json为一次全新独立运行的20条记录，单一run_id，末条complete.passed=true；不是把旧25条混合重试记录当作全通过。旧记录、旧verification与原报告已原样归档到.data/task14-keys/history/。

- 旧密钥200、恶意密钥401。
- 在全新项目proj_c8a0974d3e7e4e1bb9c314a208d2b4a9创建密钥、copy逐字相同、rename后manifest字节不变。
- 操作系统进程真实重启Dashboard，密钥和会话仍持久可读。
- 新key网关重启前401；真实重启后200，tools/list含search_memory。
- 真实只读search_memory成功；JSONL唯一run marker命中1条，tenant等于本轮新项目ID。
- revoke从配置移除；再次真实重启网关，同key401；旧密钥仍200。
- finally仅清理本轮资源；manifest回到测试前逐字节相同状态，已有凭据未被清扫。
- 两个当前验收JSON序列化后均不含凭据前缀，源码Recorder也强制拒绝不安全记录。最后一次加载最终网关源码后，旧200/恶意401再次通过。

## 检查结果

Dashboard全量287 passed（84.35秒）。密钥相关原20项加本次一致性/安全驱动7项，共27项覆盖；网关文件10项、既有契约17项、工具18项全部通过。Ruff check/format通过，pnpm verify通过；Redocly0错误、5条已有警告。前端src/shared/server/mock/.env.local相对03e10145a4dd8bc3e50b6e2a50ed788d64111945无变化；5274为sample，5276/5281为live。

## 交付与重演

版本化源码为server/backend/acceptance/probe_gateway.py与task14_driver.py；.data同名文件是安全兼容入口，旧危险脚本仅作为.pre-review.txt历史文本留档。网关补丁server/backend/patches/task14-gateway-tenants-file.patch已更新并通过reverse-check；Windows运维脚本位于本机D:/MemOS/setup/Restart-Gateway.ps1。

```powershell
cd D:\MemOS\dashboard
D:\MemOS\.venv\Scripts\python.exe -m pytest server/backend/tests -q
D:\MemOS\.venv\Scripts\python.exe -m server.backend.acceptance.probe_gateway old
D:\MemOS\.venv\Scripts\python.exe -m server.backend.acceptance.probe_gateway malicious
# 每次自动生成新run_id和新输出路径；会操作本轮隔离项目，并真实重启backend/gateway。
D:\MemOS\.venv\Scripts\python.exe -m server.backend.acceptance.task14_driver --root D:/MemOS
```

当前证据为.data/task14-keys/task14-live.json、verification.json、ledger.md；计划为docs/superpowers/plans/2026-10-27-task14-repair.md。本结论为任务14专项，不把Task15/16总验收提前视为完成。
