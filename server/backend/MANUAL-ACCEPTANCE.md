# Issue3 已实现内容与人工验收手册

更新日期：2026-10-27。当前有效入口为主站5274；早期任务报告里的“5274仍是Mock/5276单独验收”是历史状态，不能作为当前操作指引。

## 1. 当前环境与入口

| 用途 | 地址/位置 |
|---|---|
| 登录 | http://127.0.0.1:5274/__login |
| 主控制台 | http://127.0.0.1:5274/cn/memoryList |
| 退出确认 | http://127.0.0.1:5274/__logout |
| 真实模式与上游健康 | http://127.0.0.1:5274/api/meta |
| 控制台后端Swagger，供手工执行API | http://127.0.0.1:5281/docs |
| 上游原生Swagger | http://127.0.0.1:8000/docs |
| 上游健康 | http://127.0.0.1:8000/health |
| 网关健康 | http://127.0.0.1:8002/health |
| 管理员用户名 | memos-admin |
| 管理员密码 | 仅在本机 D:/MemOS/.local/dashboard-admin.json 中查看 |

统一使用127.0.0.1，不与localhost混用，避免Cookie来源不同。登录页已改为白色居中卡片、紫色按钮；退出页有确认和返回入口。登录表单仍使用CSRF，密码和会话不写入本手册。

写本手册时：5281/8000/8002健康均200，主站meta.mode=live，Mock5280不监听；当前界面选中Task10-13-a-0420c18a。

## 2. 16项工作的准确交付范围

| 任务 | 已实现内容 | 人工验收入口 |
|---|---|---|
| 1 P0运行信息 | 独立后端、统一成功/错误信封、真实上游连接检查、meta live及故障状态 | meta、真实页面、故障测试 |
| 2 P0记忆只读 | 六标签类型映射、列表/详情、项目范围、搜索/筛选/分页、字段白名单与体积限制 | 记忆列表；细筛选通过API |
| 3 P0记忆删除 | 普通记忆及画像字段软删除、恢复、回执、部分失败重试、图/向量确认 | 删除可点页面；恢复/重试通过API |
| 4 P0日志 | 同源审计JSONL增量索引、列表/详情、历史缺字段、来源/查询筛选、异步关联与1万行性能 | 调用日志、JSONL对照 |
| 5 P1用量 | 复用同一审计索引、按北京时间天聚合、日期范围、授权项目范围、缺token默认0 | 用量监控、Network |
| 6 P1项目 | 真实列表/创建/更新/切换/停用/启用/归档/恢复、重启持久化 | 项目与成员 |
| 7 P1账号 | 登录会话、当前账号、管理员账号列表/更新/启停/删除、最后有效管理员约束 | 登录及项目页“用户”标签 |
| 8 P1成员 | viewer/editor/owner、候选搜索、添加/改角色/移除/退出、最后有效owner约束 | 团队项目“成员” |
| 9 P1邀请 | 创建/角色/撤销/有效期、单次使用、登录/注册接受、过期与重用拒绝 | 成员弹窗→邀请链接；独立浏览器会话接受 |
| 10 P2知识库实体 | 保留已有实现；按用户指令冻结，不作为完整交付 | 菜单仍禁用，直达路由仅可查看已有页面 |
| 11 P2知识库文件 | 保留已有实现；按用户指令冻结，不再开发 | 不纳入本次完整人工交付签字 |
| 12 P2 Prompt | 读取/保存/真实AI生成/恢复默认/调试、真实运行时抽取生效、项目隔离 | 自定义抽取；运行时效果还需原生add验证 |
| 13 P2图谱/模型 | 真实只读来源、节点/关系投影、截断和全文、项目权限、模型配置脱敏 | 图谱、模型列表 |
| 14 P3密钥 | 持久列表/创建/改名/复制/撤销、网关文件发布、失败补偿、重启后真实可用/失效 | 接口密钥＋网关探针 |
| 15 P3模板 | 复用上游CRUD，列表/详情、字段树/分页/项目权限、持久化 | API；原前端仍为ComingSoon |
| 16汇总验收 | 停Mock主站live、页面、契约矩阵、构建/静态检查、性能、真实故障/恢复、保护目录差异 | Task16报告及本手册 |

另外补齐3个Issue允许固定返回的接口：额度、订阅、skillMD；不能把它们当作真实计费、真实配额统计或真实技能包下载。

当前本机OpenAPI有69个HTTP操作，68个有处理路由；只剩用户冻结的POST /api/dashboard/knowledgebase/memory/list无路由。“有路由”本身不是逐条业务验证结论。

## 3. 建议先完成这组只读检查

### 3.1 证明页面连接真实服务

1. 打开主站登录页，使用本机管理员凭据登录。
2. 新标签打开主站/api/meta，检查code=0、data.mode=live，以及真实上游health内容。
3. 回到控制台按F12，Network选择Fetch/XHR，勾选保留日志，刷新页面。
4. 查看/api/meta、project/dict、project/memory/list的实际Response；不能只凭页面外观判断。
5. PowerShell执行 `Get-NetTCPConnection -State Listen -LocalPort 5280 -ErrorAction SilentlyContinue`，应无监听记录。

主站响应经代理来自5281，后端再从8000查询；前端看起来可能仍像原示例页面，但数据来源已变。

### 3.2 记忆列表、搜索、详情、同ID原生对照

页面：http://127.0.0.1:5274/cn/memoryList

1. 左上角项目选择Task10-13-a-0420c18a。
2. 选“事实记忆”，在搜索框输入 `REPAIR_RULE_785229fb8e3c`，按回车提交，不能只输入而不提交。
3. 应查到真实抽取记录；打开“查看详情”，核对主体、完整正文、创建时间和记忆ID。
4. 本条验收ID为 `db0949e1-7610-4176-aa75-b5a5510f5291`。
5. 新标签打开下面原生REST地址，比较data.id及data.memory与控制台详情。原生仍为上游信封，成功码可能是200，控制台信封成功码为0。

http://127.0.0.1:8000/product/get_memory/db0949e1-7610-4176-aa75-b5a5510f5291?mem_cube_id=proj_50e0980ab13a4f1b96560b016e34c96e

正文应含项目部署南京、审计保留37天、周日03:00备份、两名owner审批等合成验收信息。可比较全文，不仅比较列表里可能已截断的预览。

6. 切换Task10-13-b-0420c18a，再搜索同一标记；不应查到A项目的这条记录。B项目可以有其他记忆，不要求B完全为空。
7. 切回A，清空搜索并按回车。逐个点击事实/偏好/事件/用户/技能/工具六个标签，观察请求里的memoryDetailType和结果。

| 页面标签 | API类型 | 来源口径 |
|---|---|---|
| 事实记忆 | text_mem | Working/LongTerm/User/OuterMemory |
| 偏好记忆 | pref_mem | PreferenceMemory |
| 事件记忆 | event_mem | EventMemory/Context/InsightMemory |
| 用户记忆 | profile_mem | 有效绑定画像中非空、未弃用、未删除字段 |
| 技能 | skill_mem | SkillMemory |
| 工具记忆 | tool_mem | ToolSchemaMemory/ToolTrajectoryMemory |

空标签是合法结果。目前没有为展示而强行给每个类型灌数据；空标签不能单独证明其非空映射正确，需结合专项测试或自己写入该类型的独立合成记录。最近一次issue3-project-a统计为事实3、用户字段4、其余0，与原生逐项一致；这些是快照，不是未来必须保持的固定数字。

8. Network中查看memory/list：数据键为memListItemResponseList，包含total/current；没有embedding/sources/history大字段。单页应小于200KiB。
9. 记忆页现有UI只有关键词、类型和分页等入口，后端还支持日期/主体/知识库元数据筛选；没有展示出来的筛选通过Swagger验证，不要寻找不存在的前端控件。
10. 当前示例项目可能少于一页，页按钮禁用合理。可在Swagger把pageSize设为1验证分页；日志页现有数据足够直接翻页。

### 3.3 调用日志与真实网关来源

页面：http://127.0.0.1:5274/cn/requests

1. 切换项目issue3-project-a。
2. 搜索 `task16-gateway-e991c8536c4c` 并按回车。
3. 应出现searchMemory/SUCCESS记录；查看详情，请求JSON包含该唯一标记。该次耗时为3109ms，这是一次模型检索耗时，不是日志列表查询耗时。
4. 点击响应详情查看原始结果。缺失Token显示0，不能据此推断模型没有成本。
5. Network打开log/detail的Response：requestBody与responseBody必须是JSON字符串；页面解码成JSON展示属于正常行为。
6. 这次记录索引ID：`log_b85aa48099e5201275d92e762ecdd4132761becf675f9a1937cffdd2659520e1`。
7. 在D:/MemOS/.local/audit下搜索上述标记，对照同一行的tool/tenant/ts/ms/ok/input；页面时间转换UTC+8，应按同一时刻核对，不要求与UTC原字符串逐字相等。来源记录位置见.data/task16/models-gateway.json。
8. 清空搜索并按回车；翻页，再打开漏斗筛选“网关/控制台/全部”、日期、主体、事件，点击应用筛选；结果应随条件改变。
9. 控制台查询、删除/恢复及故障测试本身会留下console事件；FAILURE记录不自动表示当前服务仍故障，要看时间和请求详情。

### 3.4 用量监控

页面：http://127.0.0.1:5274/cn/usage

1. 切换页面已有7/14/30天等范围按钮，查看图与日表同步变化。
2. 切换项目，确认Network请求projectId和统计范围同步变化。
3. 选一个有网关调用的日期，在日志页仅筛“网关”并使用相同项目/日期，核对addMessage与searchMemory次数。
4. 口径：北京时间自然日，只统计gateway来源；console不进入用量。成功、失败、pending等逻辑调用均计数，异步同callId合并一次。
5. 当前页面主要展示写/读次数；未知事件与缺时间行有明确排除口径。缺token为0，有可信token则保留真实值。
6. 非空apiKeyId筛选当前明确400；现有页面未使用该筛选，不能把它列成已支持能力。

### 3.5 图谱与模型

图谱：http://127.0.0.1:5274/cn/memoryGraph

选择Task10-13-a-0420c18a，点击节点，找到前面的REPAIR_RULE记录；标签可能截断，点击“展开全文”后与记忆详情同ID正文一致。切换项目图谱内容随之变化。节点时间统一UTC+8。

图谱并非无限全量：上限/预算触发时stats.truncated=true。可在Swagger调用GET graph/memories并设limit=1，观察截断标记；不要以“图上节点比数据库少”直接判断丢数据。

模型：http://127.0.0.1:5274/cn/models

应显示实际Haiku与BAAI/bge-m3相关配置；同一模型供多个角色复用时可能合并展示。Network models响应不应带API Key、URL用户名密码或敏感查询串。页面是只读清单，不是配置模型的编辑器。

## 4. 可在页面做的写操作验收

建议创建自己的MANUAL-日期前缀测试项目和账号；下述步骤由人工执行，本手册生成过程没有替你改这些资源。

### 4.1 项目生命周期

页面：http://127.0.0.1:5274/cn/projects

1. 新建MANUAL-A-日期和MANUAL-B-日期团队项目，记录不可变项目ID。
2. 编辑A名称/描述，保存后F5，值仍在。
3. 设A为当前，左上角和当前项目徽标同步；新项目记忆为空正常，不自动复制旧项目内容。
4. 停用A后，它从活跃项目下拉中消失；重新启用恢复可用。启用和设为当前是两个动作，按页面实际按钮分别验证。
5. 归档A，列表显示已归档；恢复后原ID不变。归档不是清空上游记忆。
6. 归档当前项目时，既有前端表格可能短暂缓存旧状态；F5后以真实列表及/api/auth/me.currentProjectId判断，这是已记录限制。
7. 持久化可在完成操作后运行 `D:/MemOS/setup/Restart-Backend.ps1`，重新确认项目与会话仍在。登录状态不应仅靠前端缓存维持。

### 4.2 邀请、账号、成员

1. 管理员在自己的MANUAL团队项目点击“成员”→“邀请链接”，选择viewer和有效期，生成并复制链接。
2. 使用独立浏览器配置或隐私窗口打开该链接；普通新标签页共享Cookie，不算独立账号。
3. 按邀请落地页注册一个MANUAL测试账号并接受。回到管理员窗口，应看到新成员和已使用邀请。
4. 再次打开同一链接，不能再次接受。另生成一条邀请并撤销，撤销后也不能接受。页面最短有效期是1天；秒级过期场景用Swagger的expiresIn，例如2s，等待后验证410。
5. 项目页“用户”标签可查看账号、修改显示名称、启用/禁用、平台管理员标记和删除；账号可从登录页“注册账号”入口独立注册，也可在邀请落地页注册；注册为普通账号，其他团队需另行邀请。
6. 禁用自己刚创建的测试账号，独立会话下一次API请求应401；重新启用后再登录可访问。
7. 在成员弹窗搜索已有测试账号，添加、切换viewer/editor/owner、移除。viewer可读、不可删记忆；editor可写记忆，但不能管理成员/密钥；owner管理项目资源。
8. 移除成员后，其下一次访问项目应被拒绝；退出同样撤回范围。个人空间不作为团队邀请共享。
9. 观察最后有效管理员、最后有效owner的限制：按钮可能禁用，服务端也应拒绝绕过。不要把原管理员当一次性测试账号删除。

### 4.3 密钥创建、改名、真实生效与撤销

页面：http://127.0.0.1:5274/cn/apikeys

1. 先选择自己新建的MANUAL项目，创建一把MANUAL测试密钥。
2. 页面显示掩码，Network列表按原Issue下发完整apiKey；复制功能取得完整值。
3. 改名后名称变化，凭据本身不变。F5后仍保存。
4. 新建/撤销成功发布后，已升级网关在下一次鉴权前自动重载，无需重启。首次部署自动重载代码仍需重启一次；配置发布异常会明确失败，修复后重试。
5. 在PowerShell中临时设置PROBE_TOKEN为自己创建的值，不把值写入代码或聊天。于dashboard目录执行：

```powershell
$env:PROBE_TOKEN = Read-Host '粘贴本次测试密钥'
D:/MemOS/.venv/Scripts/python.exe -m server.backend.acceptance.probe_gateway env
Remove-Item Env:PROBE_TOKEN
```

创建后直接探测应http_status=200并列出工具。撤销这把测试密钥后直接重试，同一凭据应401（env探针将以非零退出，此处正是撤销测试的预期）。无需重启网关；只清理本次创建的测试密钥，不批量撤销旧项目密钥。完整自动重演见GATEWAY-RELOAD-RESULT.md。

### 4.4 Prompt保存与调试

页面：http://127.0.0.1:5274/cn/customExtraction

1. 选择自己的MANUAL项目，复制保存当前Prompt原文。
2. 点击编辑，保留 `${conversation}` 占位符，加入明确规则，例如“只保留用户明确陈述的长期项目事实”。保存修改，F5后规则仍在。
3. 右侧输入“我的长期项目代号是MANUAL-PROJECT，部署区域固定为杭州”，运行抽取。结果来自真实配置模型，不是固定演示内容；候选可能为空，需结合Prompt与原始输出判断。
4. 返回记忆页，对比调试前后数量；调试只生成候选，不自动写入记忆。
5. AI修改会调用模型，生成后先查看，再保存。恢复默认会调用上游重置接口，并非纯本地撤销；即使随后取消编辑，也不能假定服务器规则已恢复旧值。
6. 最后把保存的原文重新保存，完成清理。
7. 要验证“保存规则影响正式入库”，还必须通过上游Swagger的POST /product/add在同一mem_cube_id写入合成对话，再到列表同ID核对；不能仅凭调试框有结果就判定正式写入链路成功。已有REPAIR_RULE记录就是该链路的实际验收证据。

## 5. 删除与恢复：页面/API联合验收

优先使用已指定的合成记录，不用前面作为长期只读演示的REPAIR_RULE记录做删除。

1. 在项目issue3-project-a的事实标签搜索 `Task03-1a180ab65165` 并回车。
2. 指定合成记录ID为 `70693895-6d13-4fd7-b55f-6faf5bc4b7f0`。先记下详情全文、ID和当前total。
3. 页面点击该记录“删除”，确认后列表不再显示；只删这一条。
4. 原生REST检查同ID：

http://127.0.0.1:8000/product/get_memory/70693895-6d13-4fd7-b55f-6faf5bc4b7f0?mem_cube_id=issue3-project-a

原生可能HTTP200但data=null；BFF详情应404。不要只检查HTTP状态码就认为仍存在。

5. 现有前端没有“恢复”按钮。打开后端Swagger的POST /api/dashboard/project/memory/restore，Try it out，输入：

```json
{
  "projectId": "issue3-project-a",
  "memory_ids": ["70693895-6d13-4fd7-b55f-6faf5bc4b7f0"],
  "memType": "text_mem"
}
```

6. Execute应返回code=0、state=confirmed、restored=1。回到正确项目的记忆页刷新，同一ID和正文恢复。
7. 若操作为pending/非零code，记录返回的operationId，使用GET operation查看及POST retry重试原操作；不能把pending视为成功。重试使用原ID，新一轮删除/恢复不要反复指定旧幂等ID；省略operationId由服务生成即可。
8. 用户画像字段同理，但memType=profile_mem、ID取该字段的真实memoryId；删除一字段不应移除同画像其他字段。恢复后值应相同。

普通页面及REST检查无法独立证明向量已同步；Network回执应有vectorState确认。独立Neo4j/Qdrant读回的既有证据见.data/task16/live.json；需要重演时使用acceptance.task16_driver，而不是以“行消失”作为全部证明。

## 6. 模板和固定接口：用Swagger验收

登录主站后，同一浏览器打开http://127.0.0.1:5281/docs，Cookie可沿用。展开接口、Try it out、填写body、Execute，检查Response body。

模板前端灰色/ComingSoon是原始前端限制，不能改src/解禁。API验证步骤：

1. POST profileTemplate/list：`{"projectId":"issue3-project-a","pageNum":1,"pageSize":10}`；返回list/total/current/size/pages，可看到现存测试模板。
2. 复制列表templateId，GET profileTemplate/detail填projectId/templateId；应返回字段树和bindingCount。
3. 如需写入，使用自己的MANUAL项目创建一个模板，内容例如：

```json
{
  "projectId": "替换为自己的MANUAL项目ID",
  "templateName": "MANUAL-template",
  "工作信息": {
    "职责": {"value": "后端开发", "algorithm_updatable": false}
  }
}
```

4. 创建返回templateId；用同ID读详情。更新时带完整当前字段树、templateName与templateId；删除时带projectId/templateId。另一项目读取/更新/删除同ID都应404。
5. 上游保留deprecated历史字段，BFF只展示有效字段；原生null默认值投影为省略可选value，不是接口失败。

三个固定接口：

| 请求 | 预期data |
|---|---|
| GET /api/user/quota/summary | 0条记忆、0个知识库、1000000容量、10个知识库额度的固定对象 |
| POST /api/user/subscription/details，body为{"cycleId":"","includeAllCycles":true} | {"cycles":[]} |
| POST /api/dashboard/skill/skillMD，body为{"oss_url":"https://example.invalid/test"} | 空字符串 |

均HTTP200/code0。不要将固定memoryCount=0与真实记忆列表3条比较后认为数据丢失：额度接口按Issue允许固定值，不是实际统计。

## 7. 性能、故障与工程质量

### 7.1 性能

- Network核对memory/list单页小于200KiB。
- 1万行JSONL首屏小于1秒，须使用专门语料测试；看当前几十行的页面速度不能替代该门槛。
- 本机三轮新索引记录805.350/779.142/795.091ms，见.data/task16/performance-faults.json。
- 可在PowerShell独立复测，不改变主站数据：

```powershell
Set-Location D:/MemOS/dashboard
@'
import sys, httpx
sys.path.insert(0, 'D:/MemOS/setup')
from verify_task04 import performance
with httpx.Client(trust_env=False, timeout=40) as client:
    print(performance(client))
'@ | D:/MemOS/.venv/Scripts/python.exe -
```

### 7.2 真实上游故障提示

仅在你准备好立即恢复的本机验收窗口操作：

1. 执行 `powershell -NoProfile -ExecutionPolicy Bypass -File D:/MemOS/setup/Restart-Upstream.ps1 -StopOnly`。
2. 刷新记忆页，预期“无法连接上游记忆服务”及重试入口，不能白屏；meta为503。
3. 执行 `powershell -NoProfile -ExecutionPolicy Bypass -File D:/MemOS/setup/Restart-Upstream.ps1`。
4. 等8000/health及主站meta恢复成功，再重试或刷新列表，数据恢复。

故障时生成的FAILURE审计记录应保留；不因恢复成功而改写旧日志。

### 7.3 工程检查

```powershell
Set-Location D:/MemOS/dashboard
D:/MemOS/.venv/Scripts/python.exe -m pytest server/backend/tests -q
D:/MemOS/.venv/Scripts/python.exe -m ruff check server/backend
pnpm verify
pnpm --package=@redocly/cli dlx redocly lint openapi.json
git diff 03e10145a4dd8bc3e50b6e2a50ed788d64111945 -- src/
```

当前最后完整后端测试304 passed。前端检查通过；Redocly允许已有5条warning但不应有error。src/差异应为空。上游只声明已运行的相关套件通过，不宣称整个上游仓库全绿。

## 8. 人工验收记录表

每项记录：项目ID、账号角色、操作时间、请求路径、code、预期/实际、必要截图；避免截图完整凭据或密码。

| 检查项 | 通过标准 | 人工结果 |
|---|---|---|
| live与停Mock | meta live；5280无监听；页面仍有真实数据 | 待填 |
| 同ID对照 | REPAIR_RULE详情与原生REST全文一致 | 待填 |
| 六标签 | 对应请求正确；有数据/空态均正常；total按范围一致 | 待填 |
| 项目隔离 | A标记在B不可见；详情不串项目 | 待填 |
| 删除恢复 | 合成记录不可见后恢复同ID同正文；回执确认 | 待填 |
| 日志 | 唯一网关标记、JSONL时间/耗时/事件对应；字符串正文 | 待填 |
| 用量 | 同项目同日网关读写次数对得上；范围切换生效 | 待填 |
| 项目 | CRUD状态、选中、归档恢复及重启持久化 | 待填 |
| 账号成员邀请 | 登录隔离、角色门禁、禁用撤权、单次邀请及最后owner/admin约束 | 待填 |
| 密钥 | 页面持久；重启后新key可用、撤销key401 | 待填 |
| Prompt | 保存后重读；真实调试不落库；正式入库另验 | 待填 |
| 图谱/模型 | 真节点全文与同ID一致；模型配置无凭据泄露 | 待填 |
| 模板API | list/detail及项目边界正确，前端仍占位 | 待填 |
| 三个固定接口 | 均200/code0、形状与固定值正确 | 待填 |
| 性能/故障 | 1万行专测达标；上游停机页面有提示，恢复后正常 | 待填 |
| 交付门槛 | verify/Redocly/测试/零src差异 | 待填 |

知识库菜单禁用、知识库memory/list缺失、用量apiKeyId限制、恢复/模板无前端按钮，继续按范围记录。没有要求通过修改前端消除这些占位。人工未执行的格子保留“待填”，不要把自动化测试通过当成人工已经签字。


## 新增：独立账号注册

登录页现有“注册账号”链接，地址http://127.0.0.1:5274/__login/register。只需账号、密码和确认密码；密码至少12字符。成功后回登录页，普通账号自动拥有个人空间，不自动加入既有团队。完整说明见REGISTRATION-RESULT.md。新增注册后最新完整后端测试为307条通过；OpenAPI新增同一路径GET/POST两个操作。
