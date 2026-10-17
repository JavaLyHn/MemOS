import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { useT, useProject } from '../lib/store'
import { LINKS } from '../lib/config'
import { Panel, PageHeader, PrimaryButton } from '../components/ui'
import { buildMcpConfig } from '../lib/quickstart-data'

function Row({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-[#f1f5f9] last:border-0">
      <span className="w-40 shrink-0 text-sm text-[#62748E]">{label}</span>
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm text-[#4044ed] hover:underline break-all">
          {value}
        </a>
      ) : (
        <code className="text-xs font-mono break-all text-[#18181b]">{value}</code>
      )}
    </div>
  )
}

export function Docs() {
  const t = useT()
  const { currentProjectId } = useProject()
  const { data } = useAsync(
    () => (currentProjectId ? api.keys.list(currentProjectId, 1, 1) : Promise.resolve({ records: [], total: 0 })),
    [currentProjectId],
  )
  const key = data?.records[0]?.apiKey ?? 'YOUR_API_KEY'

  return (
    <>
      <PageHeader
        title={t('docs.title')}
        desc={t('docs.subtitle')}
        actions={
          <a href={LINKS.home} target="_blank" rel="noopener noreferrer">
            <PrimaryButton icon="i-lucide:arrow-up-right">{t('docs.openHome')}</PrimaryButton>
          </a>
        }
      />

      <div className="flex flex-col gap-4">
        <Panel className="px-5 py-2">
          <Row label={t('docs.endpoint')} value={LINKS.home} href={LINKS.home} />
          <Row label={t('docs.mcp')} value={LINKS.mcp} />
          <Row label={t('docs.health')} value={LINKS.health} href={LINKS.health} />
        </Panel>

        <Panel className="px-5 py-4">
          <h3 className="text-sm font-semibold text-[#18181b] mb-2">{t('docs.guide')}</h3>
          <p className="text-sm text-[#62748E] mb-3">{t('quickstart.card.agentDesc')}</p>
          <pre className="rounded-[8px] border border-[#dde5f0] bg-[#fbfcfe] p-3 text-xs font-mono overflow-auto">
            {buildMcpConfig(key)}
          </pre>
        </Panel>
      </div>
    </>
  )
}
