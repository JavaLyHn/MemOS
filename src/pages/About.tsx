import { useT } from '../lib/store'
import { LINKS, SERVICE_BASE } from '../lib/config'
import { Panel, PageHeader } from '../components/ui'

export function About() {
  const t = useT()
  return (
    <>
      <PageHeader title={t('about.title')} />
      <div className="flex flex-col gap-4 max-w-[860px]">
        <Panel className="px-5 py-4 text-sm leading-6 text-[#314158]">{t('about.body')}</Panel>
        <Panel className="px-5 py-4">
          <h3 className="text-sm font-semibold text-[#18181b] mb-2">{t('about.apiContract')}</h3>
          <p className="text-sm text-[#62748E] mb-3">{t('about.apiContractBody')}</p>
          <ul className="text-sm text-[#314158] space-y-1">
            <li>
              <code className="font-mono text-xs">GET /api/keys · POST /api/keys · PATCH|DELETE /api/keys/:id</code>
            </li>
            <li>
              <code className="font-mono text-xs">GET /api/requests · GET /api/memories</code>
            </li>
            <li>
              <code className="font-mono text-xs">GET /api/models · /api/knowledge-bases · /api/profile-templates · /api/extractions</code>
            </li>
            <li>
              <code className="font-mono text-xs">GET /api/usage</code>
            </li>
          </ul>
          <p className="mt-3 text-sm text-[#62748E]">
            <a href={LINKS.docs} className="text-[#4044ed] hover:underline">
              {t('docs.title')}
            </a>
            {' · '}
            <a href={SERVICE_BASE} target="_blank" rel="noopener noreferrer" className="text-[#4044ed] hover:underline">
              {t('topbar.home')}
            </a>
          </p>
        </Panel>
      </div>
    </>
  )
}
