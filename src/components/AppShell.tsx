import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="isolate">
      <div className="flex w-screen min-w-320 max-w-full h-screen">
        <Sidebar />
        <div className="flex flex-col flex-1 min-w-0 bg-[#f0f2f5] overflow-x-auto">
          <TopBar />
          <div className="relative h-[calc(100%-56px)] flex-1 min-w-0 rounded-t-[12px] bg-white border border-white border-b-0">
            <div className="overflow-y-auto flex flex-col min-w-0 h-full p-5 rounded-t-[12px] bg-[linear-gradient(180deg,#f3f5ff_0%,#ffffff_48%)] [scrollbar-gutter:stable]">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
