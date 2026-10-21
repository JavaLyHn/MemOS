import { useT } from '../lib/store'
import { ComingSoon, PageHeader } from '../components/ui'

/** 知识库。
 *
 *  记忆服务本身没有「知识库」这个概念（上游 29 个接口里没有对应实体），所以这里**不放列表**：
 *  放一个恒为空的列表，业务会以为是坏了或者是自己没建过。
 *
 *  ⚠️ 不要再接回 `api.knowledgeBase.list`：那 8 条接口按目标约定返回空列表，
 *  渲染出来只会得到一个永远空白的表格。
 *
 *  ⚠️ 空态**不要再手写一份**：2026-10-19 之前这一页自己写了一段带 🚧 的面板，
 *  和画像模板那一页长得不一样（用户要求「建设中的文案、样式统一一点，复用组件」）。
 *  现在两页共用 `ComingSoon`，文案也共用 `common.comingSoon*`。
 *
 *  ⚠️ 外层**不要**加 `max-w-[…]`：AppShell 的内容区是 `flex flex-col h-full`，
 *  加了宽度上限会把页面卡成一条窄栏、右边整片留白（2026-10-19 用户报的布局 bug）。 */
export function KnowledgeBase() {
  const t = useT()
  return (
    <>
      <PageHeader title={t('kb.title')} />
      <ComingSoon />
    </>
  )
}
