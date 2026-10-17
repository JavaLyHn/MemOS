import { useEffect, useRef, useState, type ReactNode } from 'react'
import { TECH_CONFIG_URL, LINKS } from '../lib/config'
import { useAsync } from '../lib/useAsync'
import { useLang, useT, useToast } from '../lib/store'
import { PageHeader, Panel, StateRow, Table, TD, Th, TextLinkButton } from '../components/ui'
import { TAB_BTN, TAB_INDICATOR, TAB_STRIP } from '../lib/cls'

interface ModelRow {
  modelName: string
  provider?: string
  tags?: string[]
  isReleased?: boolean
}

const TABS = [
  { key: 'proprietary', label: 'models.tab.proprietary' },
  { key: 'chat', label: 'models.tab.chat' },
] as const

/** 能力标签的两种样式，逐字取自设计稿 */
const TAG_PRIMARY = 'inline-block h-6 px-2 text-xs font-normal border rounded-md leading-6 bg-[#eef0ff] border-[#c7c9f7] text-primary'
const TAG_PLAIN =
  'inline-block h-6 px-2 text-xs text-second-gray font-normal border-1 border-input-border rounded-md bg-[#F1F5F9] leading-6'

/** 未发布模型的「查看详情」是灰的、不可点，用另一套类名 */
const BTN_DISABLED_LINK = 'text-[14px] font-medium text-[#90A1B9] bg-transparent border-none p-0 cursor-not-allowed'

/** 模型列表走静态 JSON（形状 `{records: [...]}`），不经过后端接口 */
async function fetchModels(tab: string, lang: string): Promise<ModelRow[]> {
  const res = await fetch(`${TECH_CONFIG_URL}/${tab}.${lang}.json`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = (await res.json()) as { records?: ModelRow[] }
  return data.records ?? []
}

/** 标签条：选中项下面那条线跟着滑，位置由页面实测 */
export function Tabs({
  items,
  value,
  onChange,
}: {
  items: { key: string; label: ReactNode }[]
  value: string
  onChange: (k: string) => void
}) {
  const strip = useRef<HTMLDivElement>(null)
  const [bar, setBar] = useState({ x: 0, w: 0 })

  useEffect(() => {
    const measure = () => {
      const el = strip.current?.querySelector<HTMLElement>(`[data-tab-key="${value}"]`)
      if (el) setBar({ x: el.offsetLeft, w: el.offsetWidth })
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [value, items])

  return (
    <div className="flex items-center gap-2 flex-col w-full">
      <div ref={strip} className={TAB_STRIP}>
        <div className={TAB_INDICATOR} style={{ width: bar.w, translate: `${bar.x}px` }} />
        {items.map((x) => (
          <button
            key={x.key}
            type="button"
            data-tab-key={x.key}
            data-state={value === x.key ? 'active' : 'inactive'}
            className={TAB_BTN}
            onClick={() => onChange(x.key)}
          >
            <span className="truncate">{x.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function Models() {
  const t = useT()
  const toast = useToast()
  const { lang } = useLang()
  const [tab, setTab] = useState<string>(TABS[0].key)
  const { data, state, error } = useAsync(() => fetchModels(tab, lang), [tab, lang])

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast(t('common.copied'))
    } catch {
      toast(`${t('common.failed')}：剪贴板不可用`, 'err')
    }
  }

  const cols = 3

  return (
    <>
      <div className="flex mb-4 py-3 px-4 bg-white/80 border border-[#DADBFF] rounded-[8px] text-sm leading-5">
        <span className="text-[#314158] font-medium">{t('models.tipTitle')}</span>
        <span className="text-[#9FA1F6]">｜</span>
        <span className="text-[#62748E]">{t('models.tipText')}</span>
        <a href={LINKS.docs} rel="noopener noreferrer" target="_blank" className={`${BTN_LINK_DOC} ml-1`}>
          {t('models.viewDocs')}
        </a>
      </div>

      <PageHeader title={t('models.title')} desc={t('models.desc')} />

      <div className="flex flex-col flex-1 space-y-4 h-full">
        <Tabs items={TABS.map((x) => ({ key: x.key, label: t(x.label) }))} value={tab} onChange={setTab} />

        <div className="flex-1">
          <div className="h-full flex flex-col justify-between">
            <Panel>
              <Table
                head={
                  <>
                    <Th>{t('models.col.modelName')}</Th>
                    <Th>{t('models.col.labels')}</Th>
                    <Th>{t('models.col.action')}</Th>
                  </>
                }
              >
                {state !== 'ready' && <StateRow colSpan={cols} state={state} error={error} />}
                {state === 'ready' && data?.length === 0 && <StateRow colSpan={cols} state="ready" />}
                {state === 'ready' &&
                  data?.map((m) => {
                    const released = m.isReleased !== false
                    const tags = m.tags ?? []
                    return (
                      <tr key={m.modelName} className="data-[selected=true]:bg-elevated/50">
                        <td data-pinned="false" className={TD}>
                          <span className={released ? 'leading-5 text-second-gray' : 'leading-5 text-third-gray'}>
                            {m.modelName}
                            {released ? '' : t('models.comingSoon')}
                          </span>
                        </td>
                        <td data-pinned="false" className={TD}>
                          <div className="flex gap-2 flex-wrap">
                            {tags.map((tag, i) => (
                              <span key={tag} className={released && i === 0 ? TAG_PRIMARY : TAG_PLAIN}>
                                {tag}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td data-pinned="false" className={TD}>
                          {released ? (
                            <div className="flex gap-2">
                              <TextLinkButton onClick={() => copy(m.modelName)}>{t('models.copyModelName')}</TextLinkButton>
                              <TextLinkButton onClick={() => toast(t('models.detailTodo'))}>{t('models.viewDetails')}</TextLinkButton>
                            </div>
                          ) : (
                            <button type="button" disabled className={BTN_DISABLED_LINK}>
                              {t('models.viewDetails')}
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
              </Table>
            </Panel>
          </div>
        </div>
      </div>
    </>
  )
}

/** 提示条里的「查看文档」，文字按钮变体再加 ml-1 */
const BTN_LINK_DOC =
  'rounded-md font-medium inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors text-sm gap-1.5 text-primary hover:text-primary/75 active:text-primary/75 aria-disabled:text-primary focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary cursor-pointer p-0 disabled:text-disabled'
