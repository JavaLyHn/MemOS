# Task13：P2 图谱与模型验收结果

**最新状态（2026-10-27）：两项复核问题已修复，真实链路和页面已重新验收。当前最终结果为280项后端测试、108项上游相关回归通过；详见 [最终复验](TASK12-13-REPAIR-2026-10-27.md)。下文2026-10-26数字为首次交付快照。**
2026-10-26。任务13已交付；由主agent直接实现，无子agent。不包含P3密钥、属性树模板和任务16总验收；知识库保持用户要求的现状。

## 实现

GET /api/dashboard/graph/memories从真实/product/get_memory_graph读取激活记忆，tenant只能是当前账号可访问的Dashboard项目ID，省略时使用持久会话选择，不能传任意上游cube绕过授权。types为原生类型逗号列表，不支持的类型400；limit默认2000、范围1–2000。停用、归档、无权项目不可读。所有响应只投影约定字段，不下发embedding、sources正文、原始配置等扩展字段。

节点标签最多120个Unicode字符；后端截断或上游已截断都会正确设置labelTruncated。节点预算1MiB，连线预算750KiB且最多8000条，达到预算后stats.truncated=true；专项测试验证整体JSON小于2MiB。仅保留有效端点，映射parent/merged关系，并计算同会话星状连线、来源派生连线、连通簇与孤点统计。sourceIds保留已授权源节点携带的来源引用，不因当前页缺少来源节点篡改来源数量；绘图连线仍过滤悬空端点。

GET /api/dashboard/graph/memory按同一项目查询/product/get_memory_by_ids，mem_cube_id通过原生接口要求的query传递，正文来源与图谱一致，兼容InsightMemory等图节点。排除删除、归档与非激活节点，跨项目同ID404；全文JSON预算1MiB，超过显式413，不拿截断标签冒充全文。

GET /api/dashboard/models需要登录，允许普通账号只读部署级模型清单。数据来自真实/product/models；只允许已知4种配置来源，role/group由服务端固定映射，不信任上游额外字段。模型名禁止携带URL、查询参数或明显密钥形态；供应商只保留hostname/port，去除userinfo、路径、query和fragment；向量维度/重排后端分别按白名单投影。未知配置来源不返回，重复或畸形有效行明确502。当前真实配置为3行：Haiku记忆读取、Haiku对话、BAAI/bge-m3向量化；没有虚构未配置的重排模型。

所有接口只读、Cache-Control:no-store；身份、成员撤权沿用真实会话中间件，统一使用{code,data,message}。上游超时/业务失败返回明确错误且不回显服务商错误正文。

## 真实验收

隔离项目proj_50e0980ab13a4f1b96560b016e34c96e，limit=1时返回真实截断标记。记忆ef3c3567-e47e-4c50-9e2f-c58943f8ccba的标签120字、全文228字，Dashboard全文与同ID原生REST逐字相等，SHA256=3320a4224ea6e101ca17676ad14c78fc8e227fa24dce9010f1428623c61151e8。换另一个项目读取该ID得到404。辅助前端5276已显示真实图谱，点击节点并展开全文成功；模型页面显示实际Haiku与bge-m3清单。最终Backend重启后相同验证再次通过。

专项覆盖未知类型、limit边界、任意cube注入、匿名401、viewer跨项目、异常上游结构、删除节点、来源引用、响应体预算、只读方法、模型URL/密钥注入与配置脱敏。

最终Dashboard全量249 passed；任务12/13专项15 passed；上游相关102 passed。任务范围内Ruff check/format通过；pnpm verify通过；Redocly0错误、5条已有警告。保护目录src/shared/server/mock/.env.local相对03e10145a4dd8bc3e50b6e2a50ed788d64111945零变化，5274仍sample，5276为live。

证据位于本机.data/task10-13-p2/task13-live.json、task13-graph-fulltext.png、task13-models.png、verification.json、redocly.log；没有输出密钥、会话令牌和原业务记忆正文。真实只读复核命令：D:/MemOS/.venv/Scripts/python.exe D:/MemOS/setup/verify_task13.py。该本机脚本仅适用于已创建的隔离验收项目。

浏览器：http://127.0.0.1:5276/cn/memoryGraph 和 /cn/models。接口实现不是全库无限导出，显示统计对应返回投影，不代表截断后仍涵盖完整图。当前知识库入口仍保持既有前端状态，本任务未修改或启用它。

## 2026-10-27 图谱范围修复

早期验收只验证了普通记忆图，遗漏了独立存储的画像字段。现已补全画像合并、同 ID 全文和孤点分组，真实项目 4 条事实 + 4 条画像对应 8 个节点。详细修复与当前前端图例限制见 PROFILE-GRAPH-REPAIR.md；旧统计、端口状态和测试数量属于当时快照。
