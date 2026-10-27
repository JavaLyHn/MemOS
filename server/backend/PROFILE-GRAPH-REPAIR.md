# 画像字段图谱补全验收

日期：2026-10-27。仅修改后端与接口说明，前端 src/ 保持不变。

## 原因与修复

上游 get_memory_graph 读取普通记忆存储；画像字段由独立画像存储提供。原图谱只调用前者，导致同一项目列表中事实记忆 4 条、用户画像字段 4 条，图谱却只有 4 个节点。

后端现在按已授权项目合并普通图节点和 list_profile_memories 返回的绑定画像字段。画像保持原字段 ID 和 ProfileMemory 类型；分页每页最多 100 条，与普通节点共用 2000 节点和原有响应字节预算。普通节点先占预算，画像使用剩余配额；遗漏时明确标记 truncated。分页结构、项目归属、状态、字段 ID 和日期均校验，画像源失败不会伪装成成功的局部图。

画像全文通过同 ID 的 get_profile_memory 读取，保留统一响应、授权、404 和 1 MiB JSON 全文上限。兼容最长 1024 字符的字段 ID，OpenAPI 同步说明。敏感扩展字段不进入输出。

画像没有真实会话或关系时，sessionId/sourceIds 为空，不制造边。另修正所有孤点 clusterId 都为空字符串的问题：孤点以自己的 ID 分组，真实连通节点仍使用连通分组，避免前端把全部孤点画成同一个会话。

## 真实链路证明

项目 issue3-project-a：

- 两个列表分别 4 条；图谱 8 个节点，ID 集合严格等于两个列表的并集，truncated=false。
- 类型统计为 LongTermMemory=1、UserMemory=3、ProfileMemory=4。
- 4 个画像全文逐条与上游同 ID REST 相等；换项目访问全部 404。
- ProfileMemory 单独筛选为 4；limit=1 返回 1 且 truncated=true。
- 仅对既有 Task03 合成测试画像字段执行可恢复删除：图谱 8 → 7，全文 404；finally 恢复后 7 → 8，同 ID/全文保持一致。未删除用户手工写入的记忆。
- 后端重启后仍为同一组 8 个节点，8 个孤点分组各自独立。

证据：.data/profile-graph-repair/live.json、graph-eight.png。证据不保存正文、密钥或会话值。

## 人工检查

打开 http://127.0.0.1:5274/cn/memoryGraph，选择 issue3-project-a，刷新。左下角应为“记忆 8 · 可见 8”。点击节点检查 ID 与记忆列表一致；没有关系边的节点单独分布是正常现象。

当前前端没有 ProfileMemory 的中文图例词条，会显示 graph.type.ProfileMemory，颜色采用默认值。这是保留前端零变更的展示限制，不影响数量、字段 ID、筛选或全文。没有把画像伪装成 UserMemory 来回避该限制。

专项测试覆盖合并、205 字段跨页、类型过滤、截断、畸形/越界上游、删除恢复、长字段 ID、全文 JSON 字节预算与项目授权。质量门日志：.data/profile-graph-pytest.log、.data/profile-graph-pnpm.log、.data/profile-graph-redocly.log。

最终质量门：后端全量 318 passed（117.82 秒）；Ruff check/修改文件 format check 通过；pnpm verify 通过；Redocly 0 错误、6 条既有警告；git diff --check 通过。src/shared/server/mock/.env.local 相对 03e10145 保持空 diff。真实浏览器取消画像类型后仅显示 4 个普通节点，再勾选恢复 8 个；筛选截图见 profile-filter-off.png。
