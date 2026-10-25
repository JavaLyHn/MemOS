import type { ReactNode } from 'react'
import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Icon } from './Icon'
import { useMeta, useProject, useT } from '../lib/store'

/** 内容区骨架。
 *
 *  ⚠️ 2026-10-19 去掉了顶栏（原来 `TopBar` 渲染的面包屑 + 关于我们/帮助文档/语言切换）。
 *  它承载的三样东西都有别处可用：关于我们在侧栏账号菜单、帮助文档在侧栏导航、
 *  语言切换挪进了账号菜单。面包屑则是纯冗余——每一页自己的标题就在下面一行。
 *
 *  ⚠️ 同时去掉了内容区上的 `h-[calc(100%-56px)]`：那个 56px 就是顶栏的高度，
 *  顶栏没了还留着它，等于给页面留一条 56px 的空带。这里靠 `flex-1` 撑满
 *  （父节点是 `flex flex-col h-screen`），不再写死高度。 */
export function AppShell({ children }: { children: ReactNode }) {
  const t = useT()
  const { pathname } = useLocation()
  const { account, previewUser } = useMeta()
  const { ready, currentProjectId } = useProject()
  const showOnboarding = ready && !currentProjectId && !pathname.startsWith('/cn/projects')
  const scrollRef = useRef<HTMLDivElement>(null)

  /* 切页回到顶部。
   *
   *  滚动容器是内容区这一块，不是 window，所以浏览器不会帮我们重置：在调用日志
   *  滚到底再点侧栏的另一个页面，新页面会停在同样的高度，看起来像「没切过去」。 */
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0 })
  }, [pathname])

  return (
    <div className="isolate">
      <div className="flex w-screen min-w-320 max-w-full h-screen">
        <Sidebar />
        <main className="flex flex-col flex-1 min-w-0 bg-surface-hover overflow-x-auto">
          {previewUser && (
            <div className="shrink-0 border-b border-warning/40 bg-warning-soft px-4 py-1.5 text-center text-xs text-warning">
              {t('preview.banner')}
            </div>
          )}
          <div className="relative flex-1 min-w-0 bg-surface border-l border-line shadow-[0_1px_3px_rgba(0,0,0,0.02)]">
            <div ref={scrollRef} className="overflow-y-auto flex flex-col min-w-0 h-full p-6 bg-surface-muted/40 [scrollbar-gutter:stable]">
              {showOnboarding && (
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/30 bg-warning-soft px-4 py-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <Icon name="i-lucide:folder-plus" className="mt-0.5 size-5 shrink-0 text-warning" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink">{t('onboarding.title')}</div>
                      <div className="mt-0.5 text-xs leading-5 text-ink-secondary">
                        {t(account?.platformAdmin ? 'onboarding.descAdmin' : 'onboarding.desc')}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Link
                      to="/cn/projects"
                      className="inline-flex h-8 items-center rounded-lg border border-line bg-surface px-3 text-xs font-medium text-ink-secondary transition-colors hover:bg-surface-hover hover:text-ink"
                    >
                      {t('onboarding.go')}
                    </Link>
                    {account?.platformAdmin && (
                      <Link
                        to="/cn/projects?create=1"
                        className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-medium text-on-accent transition-colors hover:bg-accent-hover"
                      >
                        <Icon name="i-lucide:plus" className="size-3.5" />
                        {t('onboarding.create')}
                      </Link>
                    )}
                  </div>
                </div>
              )}
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
