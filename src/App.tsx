import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { DUR, EASE_IN_FAST, EASE_OUT_SOFT } from './lib/motion'
import { AppShell } from './components/AppShell'
import { LangProvider, MetaProvider, ToastProvider, ProjectProvider } from './lib/store'
import { ThemeProvider } from './lib/theme'
import { TooltipProvider } from './components/ui/tooltip'
import { ApiKeys } from './pages/ApiKeys'
import { QuickStart } from './pages/QuickStart'
import { Requests } from './pages/Requests'
import { Memories } from './pages/Memories'
import { MemoryGraph } from './pages/MemoryGraph'
import { Models } from './pages/Models'
import { KnowledgeBase } from './pages/KnowledgeBase'
import { ProfileTemplates } from './pages/ProfileTemplates'
import { Extractions } from './pages/Extractions'
import { Usage } from './pages/Usage'
import { Docs } from './pages/Docs'
import { About } from './pages/About'
import { Projects } from './pages/Projects'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000 * 30, // 30 seconds
    },
  },
})

function AnimatedRoutes() {
  const location = useLocation()
  const reduce = useReducedMotion()

  /* 页面切换：新页从下方 8px 淡入，旧页向反方向 6px 淡出。
   *
   *  两段用不同曲线——进场 `EASE_OUT_SOFT` 让内容「落定」，出场 `EASE_IN_FAST`
   *  让旧页迅速让位；反过来会变成「慢慢消失 + 突然出现」，切换显得拖沓。
   *
   *  `mode="wait"` 下两段是串行的，所以出场必须比进场短，否则每次导航都要等
   *  两个完整的时长。系统开了「减少动态效果」时只保留淡入淡出，位置不动。
   */
  const enter = reduce ? { opacity: 0 } : { opacity: 0, y: 8 }
  const exit = reduce
    ? { opacity: 0, transition: { duration: 0 } }
    : { opacity: 0, y: -6, transition: { duration: DUR.fast, ease: EASE_IN_FAST } }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={enter}
        animate={{ opacity: 1, y: 0 }}
        exit={exit}
        transition={reduce ? { duration: 0 } : { duration: DUR.page, ease: EASE_OUT_SOFT }}
        className="flex-1 flex flex-col min-h-0"
      >
        <Routes location={location}>
          <Route path="/cn/quickstart" element={<QuickStart />} />
          <Route path="/cn/apikeys" element={<ApiKeys />} />
          <Route path="/cn/requests" element={<Requests />} />
          <Route path="/cn/knowledgeBase" element={<KnowledgeBase />} />
          <Route path="/cn/memoryList" element={<Memories />} />
          <Route path="/cn/memoryGraph" element={<MemoryGraph />} />
          <Route path="/cn/models" element={<Models />} />
          <Route path="/cn/profileTemplate" element={<ProfileTemplates />} />
          <Route path="/cn/customExtraction" element={<Extractions />} />
          <Route path="/cn/projects" element={<Projects />} />
          <Route path="/cn/usage" element={<Usage />} />
          <Route path="/cn/docs" element={<Docs />} />
          <Route path="/cn/about" element={<About />} />
          <Route path="*" element={<Navigate to="/cn/apikeys" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider delayDuration={320}>
          <LangProvider>
            <MetaProvider>
              <ProjectProvider>
                <ToastProvider>
                  <AppShell>
                    <AnimatedRoutes />
                  </AppShell>
                </ToastProvider>
              </ProjectProvider>
            </MetaProvider>
          </LangProvider>
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}
