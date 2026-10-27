# Issue3 原文独立合规复核

> 后续修复：用户已要求补齐前三项。三个固定接口现已实现并通过主站200/code0契约验证；本报告下文保留修复前审查记录。知识库继续冻结。最终结果见 ISSUE3-FIXED-ENDPOINTS-RESULT.md。

2026-10-27。仅审查和记录，未修改实现。结论：当前不能认定完整达到原Issue全部要求；P0/P1主要业务链路已有验收支持，但三个固定返回接口尚未实现，原始全部接口对齐也存在冻结知识库缺口。

## 权威来源

- https://github.com/hugegraph/MemOS/issues/3 （本次通过GitHub读取正文；updated_at=2026-10-25T10:06:43Z，0评论）
- dashboard-v2/openapi.json，blob 04eea16bb8ecd603c43f7546da06260d72b7b2bc，57路径/60操作。
- dashboard-v2/src/lib/api.ts，blob 4ab6701c598a63b6df6897bc288635cf92e33969，与本机src/lib/api.ts一致。
- dashboard-v2/server/mock/server.ts；deployment-v2/docker/.env.example、src/memos/api/server_api.py、deploy/mcp-gateway/README.md。

原始OpenAPI与本机基线03e10145a4dd8bc3e50b6e2a50ed788d64111945中的openapi.json blob相同。新增恢复/回执/HTML入口后的本机69操作不能替代对原60操作逐项对齐。

## 已确认缺口

### 1. 三个“无需真实业务”的接口仍必须返回固定成功数据

Issue §2(3) 允许固定数据，并未允许接口缺失；§4要求这些接口的形状同样正确。Task16将其标成“明确豁免无路由”不准确，必须以本次复核纠正。没有必要实现计费或订阅系统，只需实现固定返回。

在已登录的主站5274实际请求，三个接口均HTTP404/code40001：

| Method | Path | 原文要求 |
|---|---|---|
| GET | /api/user/quota/summary | 成功信封，data为额度对象 |
| POST | /api/user/subscription/details | 成功信封，data为订阅周期对象 |
| POST | /api/dashboard/skill/skillMD | 成功信封，data为空字符串 |

因此，即便业务测试302条通过、Redocly通过，也不能认为§4“所有调用按定义响应”已满足。缺失接口没有被此前完整性检查判为失败，是验收规则本身的遗漏。

### 2. 知识库记忆列表未实现

POST /api/dashboard/knowledgebase/memory/list 在src/lib/api.ts中有调用、原始spec中有定义，当前无处理路由，已登录有效形状请求返回404/code40001。应当在权限和知识库归属校验后返回真实 records/total。

用户此前明确冻结知识库开发，所以此处不是未经授权继续补写的理由；但该冻结不能视为GitHub维护者对原Issue要求的豁免。知识库本身属于加分模块，完整接口对齐却明确要求api.ts里的每条调用正确。应在提交说明中如实披露，不能宣称全接口完成。

### 3. 仍保留的范围限制

- 非空usage.apiKeyId目前明确400，已在本机spec和README说明；当前用量页没有实际使用此筛选。不能宣称支持完整的按密钥统计能力。这是已声明的功能限制，不应混同前三个必须存在的固定接口。
- 知识库任务10/11未按用户冻结后的范围重新完成整套真实文件链路验收，不能仅由现有单元测试宣布知识库加分全项通过。

## 本次重新核实通过的项目

- 主站5274经真实5281，meta live；原文要求的src/零改动成立，保护目录对上述基线无diff。
- 同一项目、activated统计范围下，事实3、偏好0、事件0、技能0、工具0、画像字段4，六标签BFF条数与原生REST完全相同。
- 本次六标签10条上限请求分别1254/90/90/90/90/1555字节，均小于200KiB。空标签的非空类型映射能力由既有专项测试和各任务合成记录证据支持，不把空态说成当前每类都有真实数据。
- 17个只读请求用原始spec检查，16个零结构错误；日志因新增console事件不在原enum中而有差异。该扩展已同步本机OpenAPI，符合Issue允许“有出入同步更新spec”，不作为新增缺陷。当前契约验收见Task16证据。
- 之前Task16的新鲜证据：唯一合成记忆同ID/同正文REST对照、软删除不可读与恢复、独立图向量确认、真实网关JSONL/索引/页面同一标记、真实上游停机时错误提示及恢复、1万行三轮冷启动779–805ms。
- 项目/账号/成员/邀请权限、最后管理员/owner约束、历史缺字段、筛选分页及错误信封由302条完整后端测试及对应真链路报告支持；此轮没有再次改动所有真实管理资源。
- Task16曾实际运行pnpm verify通过、Redocly0错误5警告、相关上游104条和网关45条通过。本次是审查，不将这些称为本轮重新运行。
- 密钥、Prompt、模板、图谱与模型已有真实专项证据，分别见Task12/13修复、Task14、Task15报告。

## 不应算作缺陷的原前端限制

- ProfileTemplates.tsx本身为ComingSoon，菜单禁用；Task15已实现API列表/详情。前端不能改，不能把解禁页面列成必须修复项。
- 恢复/重试/操作查询是额外后端能力，原前端无按钮不构成原Issue新增缺口。
- 登录/登出美化只改后端生成的HTML，不违反src/零改动。
- Compose仅是原文提供的起服务方法之一；当前Windows主机运行上游和后端、Docker运行Neo4j/Qdrant，只要真实链路正确，不因未把所有服务装进同一个compose而判失败。

## 修复顺序与结论

优先补三个固定返回接口及覆盖原始60操作的完整性断言，避免再把“无需真实业务”误判为“无须接口”。然后按用户对知识库的范围决定，补齐memory/list或提交时明确说明不申请知识库完整交付。保留前端零改动。

本次没有修改实现或之前Task16验收规则；仅新增本审查文档和脱敏证据。此前“按调整范围全部完成”的结论应加上上述三个固定接口缺口，不能据此前表述提交“全部达标”。

证据目录：.data/issue3-review-20261027/baseline-contracts.json、counts-native.json、missing-endpoints.json。
