import { useT } from '../lib/store'
import { LINKS } from '../lib/config'
import { Panel, PageHeader, PrimaryButton } from '../components/ui'
import { buildMcpConfig } from '../lib/quickstart-data'

function Row({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="flex items-center gap-3 py-3 border-b border-line last:border-0">
      <span className="w-40 shrink-0 text-xs font-medium text-ink-muted">{label}</span>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-medium text-accent hover:text-accent-hover hover:underline break-all inline-flex items-center gap-1"
        >
          {value}
        </a>
      ) : (
        <code className="text-xs font-mono break-all text-ink bg-surface-hover px-1.5 py-0.5 rounded border border-line">{value}</code>
      )}
    </div>
  )
}

export function Docs() {
  const t = useT()
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

      {/* ⚠️ 必须 `flex-1 min-h-0` + 末块 `flex-1`：内容区是 `flex flex-col`，
          不加的话这两块按内容高度排完就停，窗口一高页面下半截整片空着
          （2026-10-19 全页面巡检量到 1080 高的窗口下留白 527px）。 */}
      <div className="flex flex-col gap-4 flex-1 min-h-0">
        <Panel className="px-5 py-2">
          <Row label={t('docs.endpoint')} value={LINKS.home} href={LINKS.home} />
          <Row label={t('docs.mcp')} value={LINKS.mcp} />
          <Row label={t('docs.health')} value={LINKS.health} href={LINKS.health} />
        </Panel>

        <Panel className="flex-1 min-h-0 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink mb-1">{t('docs.guide')}</h3>
          <p className="text-xs text-ink-muted mb-3">{t('docs.mcpHint')}</p>
          <pre className="rounded-xl border border-line bg-surface-muted p-4 text-xs font-mono overflow-auto text-ink leading-relaxed">
            {buildMcpConfig()}
          </pre>
        </Panel>
      </div>
    </>
  )
}
