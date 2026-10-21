import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'

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
  return (
    <div className="isolate">
      <div className="flex w-screen min-w-320 max-w-full h-screen">
        <Sidebar />
        <main className="flex flex-col flex-1 min-w-0 bg-surface-hover overflow-x-auto">
          <div className="relative flex-1 min-w-0 bg-surface border-l border-line shadow-[0_1px_3px_rgba(0,0,0,0.02)]">
            <div className="overflow-y-auto flex flex-col min-w-0 h-full p-6 bg-surface-muted/40 [scrollbar-gutter:stable]">{children}</div>
          </div>
        </main>
      </div>
    </div>
  )
}
