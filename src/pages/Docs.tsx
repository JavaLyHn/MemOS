import { useT } from '../lib/store'
import { LINKS } from '../lib/config'
import { Panel, PageHeader } from '../components/ui'
import { CopyButton } from '../components/ui/copy-button'
import { Icon } from '../components/Icon'
import { useAsync } from '../lib/useAsync'
import { api } from '../lib/api'
import { buildMcpConfig } from '../lib/quickstart-data'

/** 状态灯多久自己刷新一次。`/api/meta` 同时是后端的探针端点（日志快照 + 密钥状态 + 上游探测），
 *  不适合高频刷；一分钟一次足够让人看见变化。 */
const HEALTH_POLL_MS = 60_000

/** 上游 `/health` 的应答形如 `{"status":"healthy","service":"memos","version":"1.0.1"}`；
 *  `null` 表示后端没连上上游。字段缺失时按「取不到状态」算不健康。 */
function upstreamOk(health: Record<string, unknown> | null): boolean {
  const status = health?.status
  return typeof status === 'string' && ['ok', 'healthy', 'up'].includes(status.toLowerCase())
}

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
      <CopyButton text={href ?? value} className="ml-auto" />
    </div>
  )
}

type StatusTone = 'ok' | 'bad' | 'idle'

const DOT_CLASS: Record<StatusTone, string> = {
  ok: 'bg-success',
  bad: 'bg-danger',
  idle: 'bg-ink-faint',
}

/** 状态灯。`pulse` 只在首次探测时用：一颗会闪的灰点比一行「加载中」文字更像「正在测」。 */
function StatusDot({ tone, pulse = false }: { tone: StatusTone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex size-2.5 shrink-0">
      {pulse && <span className={`absolute inset-0 rounded-full ${DOT_CLASS[tone]} opacity-60 animate-ping`} />}
      <span className={`relative inline-flex size-2.5 rounded-full ${DOT_CLASS[tone]}`} />
    </span>
  )
}

/** 服务状态行：一盏灯代替原来的健康检查地址。
 *
 *  ⚠️ 不给业务方 URL 是有原因的：对外域名的 `/healthz` 是前置零信任网关自己的端点，
 *  恒返回 `{"status":"ok"}`，与记忆服务活不活无关；真正指向记忆服务的路径又会 302 到登录页。
 *  所以这里只认后端探测出来的结论，不把地址摆到页面上。 */
function ServiceStatus() {
  const t = useT()
  const { data, state, error, reload } = useAsync(() => api.meta(), [], {
    key: 'docs.health',
    refetchInterval: HEALTH_POLL_MS,
  })

  // 轮询失败时 TanStack Query 会保留上一次的数据，但那时候「上一次正常」已经不成立了：
  // 有 error 就按「未知」报，别拿旧数据给一颗绿点。
  const view = state === 'error' ? 'unknown' : !data ? 'checking' : upstreamOk(data.health) ? 'ok' : 'bad'
  const tone: StatusTone = view === 'ok' ? 'ok' : view === 'bad' ? 'bad' : 'idle'
  const label =
    view === 'checking'
      ? t('docs.statusChecking')
      : view === 'ok'
        ? t('docs.statusOk')
        : view === 'bad'
          ? t('docs.statusBad')
          : t('docs.statusUnknown')

  const hint =
    state === 'error'
      ? error
      : data
        ? `${t('docs.upstream')}：${upstreamOk(data.health) ? t('docs.checkOk') : t('docs.checkDown')}`
        : undefined

  return (
    <div className="flex items-center gap-3 py-3">
      <span className="w-40 shrink-0 text-xs font-medium text-ink-muted">{t('docs.status')}</span>
      <span className="inline-flex items-center gap-2 text-xs font-medium text-ink" title={hint}>
        <StatusDot tone={tone} pulse={view === 'checking'} />
        {label}
      </span>
      <span className="ml-auto flex items-center gap-2 text-[11px] text-ink-faint">
        <button
          type="button"
          onClick={reload}
          title={t('docs.refresh')}
          aria-label={t('docs.refresh')}
          className="inline-flex size-6 items-center justify-center rounded-md text-ink-faint hover:bg-surface-hover hover:text-ink-secondary transition-colors cursor-pointer"
        >
          <Icon name="i-lucide:rotate-ccw" className="size-3.5" />
        </button>
      </span>
    </div>
  )
}

export function Docs() {
  const t = useT()
  return (
    <>
      <PageHeader title={t('docs.title')} desc={t('docs.subtitle')} />

      {/* ⚠️ 必须 `flex-1 min-h-0` + 末块 `flex-1`：内容区是 `flex flex-col`，
          不加的话这两块按内容高度排完就停，窗口一高页面下半截整片空着
          （2026-10-19 全页面巡检量到 1080 高的窗口下留白 527px）。 */}
      <div className="flex flex-col gap-4 flex-1 min-h-0">
        <Panel className="px-5 py-2">
          <Row label={t('docs.mcp')} value={LINKS.mcp} />
          <ServiceStatus />
        </Panel>

        <Panel className="flex-1 min-h-0 px-5 py-4">
          <h3 className="text-sm font-semibold text-ink mb-1">{t('docs.guide')}</h3>
          <p className="text-xs text-ink-muted mb-3">{t('docs.mcpHint')}</p>
          <div className="relative">
            <pre className="rounded-xl border border-line bg-surface-muted p-4 pr-11 text-xs font-mono overflow-auto text-ink leading-relaxed">
              {buildMcpConfig()}
            </pre>
            <CopyButton text={buildMcpConfig()} className="absolute right-2 top-2" />
          </div>
        </Panel>
      </div>
    </>
  )
}
