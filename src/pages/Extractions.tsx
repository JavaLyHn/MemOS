/** 自定义抽取。左栏只读 Prompt，右栏快速调试。 */

import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Dialog, PageHeader } from '../components/ui'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Icon } from '../components/Icon'
import { useProject, useT, useToast, useLang } from '../lib/store'
import { errText } from '../lib/i18n'

interface ExtractResult {
  type?: string
  content?: string
}

/** 测试输入的长度上限。样例文本本身走文案字典（`extraction.sample`），
 *  它在英文界面下也该是英文。 */
const MAX_INPUT = 500

const PROMPT_VIEW =
  'ce-textarea block w-full flex-1 rounded-lg border border-line px-3.5 py-3 text-xs leading-6 font-mono outline-none min-h-[220px] resize-none bg-surface-muted text-ink-secondary cursor-default'
const PROMPT_EDIT =
  'ce-textarea block w-full flex-1 rounded-lg border border-line px-3.5 py-3 text-xs leading-6 font-mono outline-none min-h-[220px] resize-y bg-surface text-ink focus:ring-2 focus:ring-accent/20 focus:border-accent'
const DEBUG_INPUT =
  'ce-textarea flex-1 block w-full rounded-lg border border-line bg-surface px-3.5 py-3 text-xs leading-6 resize-none outline-none hover:border-line-strong focus:ring-2 focus:ring-accent/20 focus:border-accent text-ink'

const CARD = 'flex flex-col rounded-xl border border-line bg-surface min-h-0 shadow-2xs'
const CARD_HEAD = 'flex items-center justify-between px-5 py-3.5 border-b border-line'
const CARD_TITLE = 'text-xs font-semibold text-ink'

/** 卡片里的小标题与右上角计数 */
const MINI_TITLE = 'text-xs font-medium text-third-gray'
const MINI_META = 'text-[11px] text-ink-faint'

export function Extractions() {
  const t = useT()
  const { lang } = useLang()
  const toast = useToast()
  const { currentProjectId } = useProject()

  const [prompt, setPrompt] = useState('')
  const [saved, setSaved] = useState('')
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [customSample, setCustomSample] = useState<string | null>(null)
  const [results, setResults] = useState<ExtractResult[] | null>(null)

  const activeSample = customSample ?? t('extraction.sample')

  /** 「AI 修改」要问的那句话。默认值就是原来写死的那句，用户可改。 */
  const [aiOpen, setAiOpen] = useState(false)
  const [aiAsk, setAiAsk] = useState('')

  useEffect(() => {
    if (!currentProjectId) return
    let alive = true
    api.promptConfig
      .detail({ projectId: currentProjectId })
      .then((d) => {
        if (!alive) return
        const p = String(d.prompt ?? '')
        setPrompt(p)
        setSaved(p)
      })
      .catch(() => {
        if (alive) {
          setPrompt('')
          setSaved('')
        }
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [currentProjectId])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      toast(errText(lang, e), 'err')
    } finally {
      setBusy(false)
    }
  }

  const save = () =>
    run(async () => {
      await api.promptConfig.save({ projectId: currentProjectId, prompt })
      setSaved(prompt)
      setEditing(false)
      toast(t('extraction.saved'))
    })

  /** 「AI 修改」：让服务端按一句话要求重写 Prompt。
   *
   *  ⚠️ 原来这句要求是**写死的**（`extraction.aiHint`），点一下按钮就发出去，
   *  界面上没有任何地方能看出「它到底要按什么改」。用户点下去只会看到整段 Prompt
   *  被换掉，而且换的方向是别人定的。现在先弹一个输入框，默认值就是原来那句，
   *  不想要可以直接改——按钮的效果因此变成可见的。 */
  const aiRewrite = () =>
    run(async () => {
      const d = await api.promptConfig.generate({ projectId: currentProjectId, description: aiAsk })
      const next = String(d.prompt ?? '')
      if (next) setPrompt(next)
      setAiOpen(false)
    })

  const resetDefault = () =>
    run(async () => {
      const d = await api.promptConfig.resetDefault({ projectId: currentProjectId })
      setPrompt(String(d.prompt ?? ''))
    })

  const debug = () =>
    run(async () => {
      const d = await api.promptConfig.debugExtract({
        projectId: currentProjectId,
        messages: [{ role: 'user', content: activeSample }],
      })
      setResults((d.results as ExtractResult[]) ?? [])
    })

  const dirty = prompt !== saved

  return (
    <>
      <PageHeader title={t('extraction.title')} desc={t('extraction.desc')} />

      <div className="flex flex-col flex-1 min-h-0">
        <div data-v-d90ff256="" className="flex flex-col min-h-0 h-full custom-extraction">
          <div className="grid flex-1 min-h-0 gap-4 lg:grid-cols-2">
            {/* 左：Prompt */}
            <section data-v-d90ff256="" className="flex flex-col rounded-lg border border-line bg-surface relative min-h-0">
              <div data-v-d90ff256="" className={CARD_HEAD}>
                <div className="flex items-center gap-2">
                  <h3 data-v-d90ff256="" className={CARD_TITLE}>
                    {t('extraction.promptTitle')}
                  </h3>
                </div>
                {!editing && (
                  <Button variant="primary" size="sm" disabled={busy || !currentProjectId} onClick={() => setEditing(true)}>
                    {t('extraction.edit')}
                  </Button>
                )}
              </div>
              <div data-v-d90ff256="" className="flex-1 flex flex-col p-5 min-h-0 overflow-y-auto">
                {loading ? (
                  <div className="flex-1 space-y-3 p-2 min-h-[220px]">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-5/6" />
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-4 w-4/5" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                ) : (
                  <textarea
                    data-v-d90ff256=""
                    readOnly={!editing}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    className={editing ? PROMPT_EDIT : PROMPT_VIEW}
                  />
                )}
                {editing && (
                  <div data-v-d90ff256="" className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        onClick={() => {
                          setAiAsk(t('extraction.aiHint'))
                          setAiOpen(true)
                        }}
                      >
                        <Icon name="i-lucide:sparkles" className="shrink-0 size-3.5" />
                        {t('extraction.aiRewrite')}
                      </Button>
                      <Button variant="ghost" size="sm" disabled={busy} onClick={resetDefault}>
                        {t('extraction.resetDefault')}
                      </Button>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          setPrompt(saved)
                          setEditing(false)
                        }}
                      >
                        {t('extraction.cancel')}
                      </Button>
                      <Button variant="primary" size="sm" disabled={busy || !dirty} onClick={save}>
                        {t('extraction.saveEdit')}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* 右：快速调试 */}
            <div data-v-d90ff256="" className={`${CARD} gap-4`}>
              <div data-v-d90ff256="" className={CARD_HEAD}>
                <h3 data-v-d90ff256="" className={CARD_TITLE}>
                  {t('extraction.debugTitle')}
                </h3>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setCustomSample(null)
                    }}
                  >
                    {t('extraction.restoreSample')}
                  </Button>
                  <Button variant="primary" size="sm" disabled={busy || !currentProjectId} onClick={debug}>
                    <Icon name="i-lucide:play" className="shrink-0 size-3.5" />
                    {t('extraction.debugRun')}
                  </Button>
                </div>
              </div>

              <div data-v-d90ff256="" className="flex flex-col flex-1 px-5 min-h-0">
                <div data-v-d90ff256="" className="flex items-center justify-between mb-2">
                  <p data-v-d90ff256="" className={MINI_TITLE}>
                    {t('extraction.testInput')}
                  </p>
                  <span data-v-d90ff256="" className={MINI_META}>
                    {activeSample.length}/{MAX_INPUT}
                  </span>
                </div>
                <textarea
                  data-v-d90ff256=""
                  value={activeSample}
                  maxLength={MAX_INPUT}
                  onChange={(e) => {
                    setCustomSample(e.target.value)
                  }}
                  placeholder={t('extraction.debugInput')}
                  className={DEBUG_INPUT}
                />
              </div>

              <div data-v-d90ff256="" className="flex flex-col flex-1 border-t border-line min-h-0">
                <div data-v-d90ff256="" className="flex items-center justify-between px-5 py-3">
                  <p data-v-d90ff256="" className={MINI_TITLE}>
                    {t('extraction.resultTitle')}
                  </p>
                  <span data-v-d90ff256="" className={MINI_META}>
                    {t('extraction.resultPreview')}
                  </span>
                </div>
                {results && results.length > 0 ? (
                  <div className="flex-1 overflow-y-auto px-5 pb-5 space-y-2">
                    {results.map((r, i) => (
                      <div key={i} className="rounded-lg border border-line bg-surface-muted/60 px-3.5 py-3 text-xs leading-6 text-ink">
                        {r.type && (
                          <span className="mr-2 rounded-md border border-accent/30 bg-accent-soft px-2 py-0.5 font-mono text-xs text-accent font-medium">
                            {r.type}
                          </span>
                        )}
                        <span>{r.content}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div data-v-d90ff256="" className="flex-1 flex flex-col items-center justify-center px-6 text-center">
                    <Icon name="i-lucide:file-search" className="mb-2.5 h-6 w-6 text-ink-faint" />
                    <div data-v-d90ff256="" className="text-xs text-ink-faint">
                      {results ? t('common.empty') : t('extraction.resultEmpty')}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <Dialog
          open={aiOpen}
          title={t('extraction.aiTitle')}
          onClose={() => setAiOpen(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setAiOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button variant="primary" disabled={busy || !aiAsk.trim()} onClick={aiRewrite}>
                {t('extraction.aiSubmit')}
              </Button>
            </>
          }
        >
          <div className="flex flex-col gap-3">
            <p className="text-sm leading-6 text-ink-muted">{t('extraction.aiDesc')}</p>
            <textarea
              value={aiAsk}
              onChange={(e) => setAiAsk(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-line px-3 py-2 text-[13px] leading-6 outline-none focus:border-primary focus:ring-2 focus:ring-primary/40"
            />
          </div>
        </Dialog>
      </div>
    </>
  )
}
