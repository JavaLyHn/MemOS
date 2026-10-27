# Task12：P2 Prompt 验收结果

**最新状态（2026-10-27）：两项复核问题已修复，真实链路和页面已重新验收。当前最终结果为280项后端测试、108项上游相关回归通过；详见 [最终复验](TASK12-13-REPAIR-2026-10-27.md)。下文2026-10-26数字为首次交付快照。**
2026-10-26。任务12已交付；本轮由主agent直接实现，无子agent。知识库实体与文件按用户要求冻结现状。本报告不宣称整个Issue3或任务16已经完成。

## 行为与权限

| 接口（前缀 `/api/dashboard/prompt-config`） | 行为 | 最低权限 |
|---|---|---|
| POST `/detail` | 从真实上游读取项目已保存模板或默认模板 | viewer |
| POST `/save` | 保存整个模板，必须包含 `${conversation}`，最长20000字 | owner |
| POST `/generate` | 使用真实模型按描述生成候选模板，不自动保存 | editor |
| POST `/reset-default` | 删除项目自定义配置并返回上游默认模板 | owner |
| POST `/debug/extract` | 用项目当前模板调用真实模型，返回候选，不写记忆 | editor |

所有接口要求真实登录会话和可访问、未停用/归档的项目。请求禁止额外字段；生成描述最长2000字；调试消息1–30条，每条最长20000字。extractionTypes仅接受text_mem/pref_mem/event_mem，空数组使用默认三类。返回类型映射原生记忆类型；非结构模型输出明确标记raw。普通读取与保存使用上游请求超时，生成/调试使用独立120秒总截止时间，可通过DASHBOARD_MODEL_TIMEOUT_SECONDS配置，最大180秒。模型异常、HTTP200业务失败和模板占位符丢失返回明确失败，不回显服务商错误或密钥，不隐式重试收费调用。

## 真实抽取生效的修复与证据

验收发现两处实际断点：多模态读取器覆盖父类方法后只选内置模板；模型返回memory_list时调试器能识别、真实读取器却只识别memory list。现在真实chat抽取读取项目ContextVar模板，并兼容两种键名。多项目fan-out还会逐cube载入各自模板，避免把第一个项目的规则串到后续项目。文档抽取仍使用原有文档模板。

改动仅涉及上游内部multi_modal_struct.py和composite_cube.py及新增回归测试，没有新增上游公共API或数据库迁移。上游补丁保存在patches/task12-upstream-prompt-runtime.patch，针对deployment-v2本机基线8d6e231d7d95ea29b6a2716c9c34837644d3e7f6；已通过git apply --reverse --check。本任务部署需要该补丁生效并重启上游，仅复制Dashboard适配器不能修复上游真实抽取。

隔离项目proj_50e0980ab13a4f1b96560b016e34c96e中，RULE_PREFIX_0420c18a只写在保存的Prompt，不在对话输入。真实/product/add同步fine抽取后，Dashboard按该标记查到记忆ef3c3567-e47e-4c50-9e2f-c58943f8ccba；再按同一ID读取上游REST，正文确实包含规则前缀。生成候选没有改写原配置，另一个项目的Prompt哈希未变，完成后隔离项目已恢复默认。

辅助前端5276实际完成编辑、保存、恢复默认与重新读取；另用中文合成发布约定触发真实调试，页面显示4条text_mem候选。调试前后隔离项目的活动记忆均为2条，证明调试未落库。原有业务项目与Prompt未修改。隔离项目保留2条明确标记的合成记忆供复核，其中1条为早期失败探针、1条为最终规则生效证据。

## 测试与复核

新增回归先观察失败再修复，覆盖模板传播、工作线程复用不串规则、未配置项目回退、文档模板独立、multi-cube隔离及键名兼容。Dashboard专项还覆盖读取/保存/生成/重置/调试、角色和跨项目、停用项目、占位符、上游故障与脱敏。

最终Dashboard全量249 passed；任务12/13专项15 passed；上游相关102 passed。本任务Dashboard七个文件与上游三个文件Ruff check/format均通过；按改动范围执行上游make format中的Ruff命令，避免全仓自动修改无关文件。pnpm verify通过；Redocly为0错误、5条既有警告（license、localhost、3条HTML成功303）；src/shared/server/mock/.env.local相对基线03e10145a4dd8bc3e50b6e2a50ed788d64111945零变化。主5274保持sample，辅助5276为live。

本机证据：.data/task10-13-p2/task12-live.json、task12-prompt-debug.png、verification.json。命令：python -m pytest server/backend/tests -q。真实模型验收脚本为本机D:/MemOS/setup/verify_task12.py，执行会修改隔离测试项目Prompt并可能产生收费调用，不属于默认单元测试。

浏览器复核：http://127.0.0.1:5276/cn/customExtraction，使用现有账号登录，选择Task10-13-a-0420c18a。生成候选仍需点保存才改变真实抽取；快速调试使用服务端已保存模板，编辑区未保存文本不生效，这是当前前端既有交互。
