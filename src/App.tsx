import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
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
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.16, ease: 'easeOut' }}
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
