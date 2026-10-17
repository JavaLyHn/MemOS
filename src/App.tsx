import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { LangProvider, MetaProvider, ToastProvider, ProjectProvider } from './lib/store'
import { ApiKeys } from './pages/ApiKeys'
import { QuickStart } from './pages/QuickStart'
import { Requests } from './pages/Requests'
import { Memories } from './pages/Memories'
import { Models } from './pages/Models'
import { KnowledgeBase } from './pages/KnowledgeBase'
import { ProfileTemplates } from './pages/ProfileTemplates'
import { ProfileTemplateDetail, ProfileTemplateNew } from './pages/ProfileTemplateForm'
import { Extractions } from './pages/Extractions'
import { Usage } from './pages/Usage'
import { Docs } from './pages/Docs'
import { About } from './pages/About'

export default function App() {
  return (
    <LangProvider>
      <MetaProvider>
        <ProjectProvider>
          <ToastProvider>
            <AppShell>
              <Routes>
                <Route path="/cn/quickstart" element={<QuickStart />} />
                <Route path="/cn/apikeys" element={<ApiKeys />} />
                <Route path="/cn/requests" element={<Requests />} />
                <Route path="/cn/knowledgeBase" element={<KnowledgeBase />} />
                <Route path="/cn/memoryList" element={<Memories />} />
                <Route path="/cn/models" element={<Models />} />
                <Route path="/cn/profileTemplate" element={<ProfileTemplates />} />
                <Route path="/cn/profileTemplate/new" element={<ProfileTemplateNew />} />
                <Route path="/cn/profileTemplate/:templateId" element={<ProfileTemplateDetail />} />
                <Route path="/cn/customExtraction" element={<Extractions />} />
                <Route path="/cn/usage" element={<Usage />} />
                <Route path="/cn/docs" element={<Docs />} />
                <Route path="/cn/about" element={<About />} />
                <Route path="*" element={<Navigate to="/cn/apikeys" replace />} />
              </Routes>
            </AppShell>
          </ToastProvider>
        </ProjectProvider>
      </MetaProvider>
    </LangProvider>
  )
}
