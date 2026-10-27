# Task15 属性树模板交付

2026-10-27。主 agent 实现，无子 agent，未提交代码。

## 已完成

五个约定接口均复用上游真实 profile 服务：POST list/create/update/delete，GET detail。项目映射由控制存储解析；viewer 可读，owner 可写；停用、归档、未授权项目不可访问。

列表按契约输出 list/current/size/total/pages；详情将 profile_template_id/name/metadata/bound_count/updated_at 投影为 templateId/templateName/动态字段树/bindingCount/updatedAt。更新时间统一 UTC+8。未知上游字段不下发。创建返回 templateId，更新/删除返回空对象成功信封。

上游更新保留 deprecated 历史字段，适配层仅投影当前字段，不改历史数据；删除沿用上游语义，已绑定画像变为 detached，不销毁其历史值。

## 验证

- 12 条专项测试通过：契约、空态、分页、CRUD、跨项目三种操作拒绝、viewer 写拒绝、未知项目、输入校验、非法上游响应、deprecated 投影、原生 null 默认值兼容及源数据不变。
- 实际后端5281→上游8000，8个检查全部通过，证据 `.data/task15/706769ba885e.json`。
- 独有 TASK15 标记创建；BFF与原生REST同一模板ID和字段树；分页中可找到；另一项目详情/更新/删除均404；更新移除字段后原生保留deprecated、BFF不再展示。
- 后端与上游分别真正重启后仍能读回同ID更新内容；之后删除并验证两侧均不可见。最终通过运行的测试模板已删除。
- 可重演入口：`python -m server.backend.acceptance.task15_driver --project <projectId> --other-project <otherProjectId> --cube <upstreamCubeId> --restart`。使用本机已有管理员文件，不输出凭据。

## 限制

`src/pages/ProfileTemplates.tsx` 仍是 ComingSoon，菜单仍禁用，没有列表编辑 UI；本任务交付 API 能力，不把占位页称为可操作页面。未修改 src/、shared/、Mock或OpenAPI。

Dashboard契约为两层“组→字段→字符串/布尔叶子”，不开放原生三层或任意JSON值。限制50组、500字段、单值4000字符、规范化树128KiB；禁止点号路径和与上游叶子标记冲突的字段名。create不接受templateId/bindingCount/updatedAt伪造字段；update要求完整当前树与名称。未增加绑定接口或模板编辑前端。

原生历史模板允许 value:null 表示未设置默认值，投影时省略契约可选的字符串 value 字段，保留 algorithm_updatable；不写回、不把 null 文本化。issue3-project-a 的历史模板列表已实测通过。先前一次重启就绪等待失败留下的本次自建模板也已按记录 ID 定向清理。

前置登录/退出界面同时完成：居中白卡片、控制台紫色按钮、显式标签、返回入口；样式用CSP哈希授权，脚本仍禁止。19条既有认证/邀请回归通过，实际浏览器截图见 `.data/auth-ui/login.png` 与 `logout.png`。
