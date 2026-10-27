# Issue3 固定接口补齐

2026-10-27。按用户授权，仅补齐前三个固定接口；知识库实现保持不变。未提交代码。

## 行为

| 接口 | 成功data |
|---|---|
| GET /api/user/quota/summary | memoryCount=0、knowledgebaseCount=0、knowledgebaseCapacity=1000000、allowedKnowledgebaseCount=10 |
| POST /api/user/subscription/details | cycles=[] |
| POST /api/dashboard/skill/skillMD | 空字符串 |

均使用HTTP200与code=0/data/message信封，Cache-Control:no-store。额度数值是Issue允许的固定展示数据，不是实际容量或记忆统计。订阅无有效周期，因此不伪造currentCycle或账期日期。knowledgebaseId/cycleId参数不触发知识库查询或计费业务；skillMD不下载oss_url。用量统计逻辑未改动。

保留既有鉴权：skillMD属于/api/dashboard/受会话及同源中间件保护；额度/订阅只返回公开固定值，沿用其原始OpenAPI未要求认证的定义。请求体由严格类型验证，非法输入仍返回统一错误信封。

## 实现与验收修正

- compatibility.py独立管理三个固定响应，app.py注册路由；没有改变OpenAPI、src/、Mock或知识库代码。
- 两个专项测试先复现404与缺失路由，再通过：固定返回/JSON Schema/空值及类型边界/鉴权/不访问上游，以及全spec接口存在性。
- 完整性断言现在只允许用户明确冻结的POST /api/dashboard/knowledgebase/memory/list无路由；三个固定接口不再豁免。Task16重演脚本同时加入三个固定响应的真实契约检查。
- 当前69个操作中68个有处理路由；54个业务实现、3个固定接口、12个冻结知识库操作（11个已有路由）。原始60操作中的固定接口缺口已经关闭。

## 实际验证

- 后端已受控重启；通过主站5274实际请求三个接口，全部HTTP200/code0，并通过openapi.json对应响应JSON Schema。
- 证据：.data/issue3-review-20261027/fixed-endpoints-live.json。
- 专项2 passed；完整后端304 passed，92.03秒，见同目录pytest-fixed.log。Ruff全量和本轮4个Python文件格式检查通过；保护目录对03e10145a4dd8bc3e50b6e2a50ed788d64111945无差异。

知识库冻结项及之前已说明的其他功能限制仍保留，不把本次三个固定接口补齐称为知识库完整交付。
