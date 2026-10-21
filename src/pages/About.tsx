import { useT } from '../lib/store'
import { Panel, PageHeader } from '../components/ui'

/** 关于我们。
 *
 *  ⚠️ 这一页**只写能当场核对的事**，而且是关于**这个控制台**的事。
 *  2026-10-19 的第一版列过「记忆沉淀 / 语义检索 / 画像与偏好 / 多租户隔离 / 调用可观测」，
 *  那是**记忆服务**的能力，不是控制台的：控制台自己不抽取、不检索、不生成画像。
 *  列在这里等于替别人的能力背书，业务点进来一条都验不了（用户的原话：
 *  「要是没得写，你就别写什么实质性的东西」）。
 *  现在改成「这个控制台里有哪几页、每页能干什么」——逐条点开侧边栏就能对上。
 *
 *  ⚠️ 这里也不要写「接口路径见 openapi.json / 前端接口在 src/lib/api.ts」这类内部实现细节，
 *  那是给维护同学看的。维护向的排障入口在业务操作手册里。
 *
 *  ⚠️ 外层**不要**加 `max-w-[…]`：AppShell 的内容区是 `flex flex-col h-full`，
 *  加了宽度上限会把页面卡成一条窄栏、右边整片留白（2026-10-19 用户报的布局 bug）。
 *  页面清单用两列网格铺开，避免文字只占左半边。 */
export function About() {
  const t = useT()
  const pages = [
    'about.page.memories',
    'about.page.requests',
    'about.page.graph',
    'about.page.usage',
    'about.page.keys',
    'about.page.extraction',
  ] as const

  return (
    <>
      <PageHeader title={t('about.title')} />
      <div className="flex flex-col gap-4 flex-1 min-h-0">
        <Panel className="shrink-0 px-5 py-4 text-sm leading-6 text-ink-secondary">{t('about.body')}</Panel>
        <Panel className="flex-1 min-h-0 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink mb-3">{t('about.pages')}</h3>
          <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2 xl:grid-cols-3">
            {pages.map((k) => (
              <li key={k} className="text-sm leading-6 text-ink-secondary">
                {t(k)}
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </>
  )
}
