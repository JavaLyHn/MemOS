/** 自定义抽取。左栏只读 Prompt，右栏快速调试。 */

import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { PageHeader } from '../components/ui'
import { Icon } from '../components/Icon'
import { BTN_FILTER, BTN_SM_OUTLINE, BTN_SM_TEXT } from '../lib/cls'
import { useProject, useT, useToast } from '../lib/store'

interface ExtractResult {
  type?: string
  content?: string
}

/** 测试输入的样例与长度上限 */
const SAMPLE = '用户：帮我把这次的线上问题整理成复盘材料，结论先行，给出可量化的数字。'
const MAX_INPUT = 500

const PROMPT_VIEW =
  'ce-textarea block w-full flex-1 rounded-md border px-3.5 py-3 text-[13px] leading-6 font-mono outline-none min-h-[220px] resize-none bg-[#F8FAFC] border-transparent cursor-default'
const PROMPT_EDIT =
  'ce-textarea block w-full flex-1 rounded-md border px-3.5 py-3 text-[13px] leading-6 font-mono outline-none min-h-[220px] resize-y bg-white border-[#E2E8F0] focus:ring-2 focus:ring-primary/40 focus:border-primary'
const DEBUG_INPUT =
  'ce-textarea flex-1 block w-full rounded-md border border-[#E2E8F0] bg-white px-3.5 py-3 text-[13px] leading-6 resize-none outline-none hover:border-[#CBD5E1] focus:ring-2 focus:ring-primary/40 focus:border-primary'

const CARD = 'flex flex-col rounded-lg border border-[#E2E8F0] bg-white min-h-0'
const CARD_HEAD = 'flex items-center justify-between px-5 py-3.5 border-b border-[#F1F5F9]'
const CARD_TITLE = 'text-[13px] font-semibold text-second-gray'

/** 卡片里的小标题与右上角计数 */
const MINI_TITLE = 'text-xs font-medium text-third-gray'
const MINI_META = 'text-[11px] text-[#94A3B8]'

export function Extractions() {
  const t = useT()
  const toast = useToast()
  const { currentProjectId } = useProject()

  const [prompt, setPrompt] = useState('')
  const [saved, setSaved] = useState('')
  const [editing, setEditing] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)

  const [sample, setSample] = useState(SAMPLE)
  const [results, setResults] = useState<ExtractResult[] | null>(null)

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
      toast(e instanceof Error ? e.message : String(e), 'err')
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

  /** 「AI 修改」：让服务端按一句话要求重写 Prompt */
  const aiRewrite = () =>
    run(async () => {
      const d = await api.promptConfig.generate({
        projectId: currentProjectId,
        description: t('extraction.aiHint'),
      })
      const next = String(d.prompt ?? '')
      if (next) setPrompt(next)
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
        messages: [{ role: 'user', content: sample }],
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
            <section data-v-d90ff256="" className="flex flex-col rounded-lg border border-[#E2E8F0] bg-white relative min-h-0">
              <div data-v-d90ff256="" className={CARD_HEAD}>
                <div className="flex items-center gap-2">
                  <h3 data-v-d90ff256="" className={CARD_TITLE}>
                    {t('extraction.promptTitle')}
                  </h3>
                </div>
                {!editing && (
                  <button type="button" className={BTN_FILTER} disabled={busy || !currentProjectId} onClick={() => setEditing(true)}>
                    {t('extraction.edit')}
                  </button>
                )}
              </div>
              <div data-v-d90ff256="" className="flex-1 flex flex-col p-5 min-h-0 overflow-y-auto">
                <textarea
                  data-v-d90ff256=""
                  readOnly={!editing}
                  value={loading ? t('common.loading') : prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className={editing ? PROMPT_EDIT : PROMPT_VIEW}
                />
                {editing && (
                  <div data-v-d90ff256="" className="flex items-center justify-between mt-3">
                    <div className="flex items-center gap-2">
                      <button type="button" className={BTN_SM_OUTLINE} disabled={busy} onClick={aiRewrite}>
                        <Icon name="i-lucide:sparkles" className="shrink-0 size-4" />
                        {t('extraction.aiRewrite')}
                      </button>
                      <button type="button" className={BTN_SM_TEXT} disabled={busy} onClick={resetDefault}>
                        {t('extraction.resetDefault')}
                      </button>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className={BTN_SM_OUTLINE}
                        onClick={() => {
                          setPrompt(saved)
                          setEditing(false)
                        }}
                      >
                        {t('extraction.cancel')}
                      </button>
                      <button type="button" className={BTN_FILTER} disabled={busy || !dirty} onClick={save}>
                        {t('extraction.saveEdit')}
                      </button>
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
                  <button type="button" className={BTN_SM_TEXT} onClick={() => setSample(SAMPLE)}>
                    {t('extraction.restoreSample')}
                  </button>
                  <button type="button" className={BTN_FILTER} disabled={busy || !currentProjectId} onClick={debug}>
                    <Icon name="i-lucide:play" className="shrink-0 size-4" />
                    {t('extraction.debugRun')}
                  </button>
                </div>
              </div>

              <div data-v-d90ff256="" className="flex flex-col flex-1 px-5 min-h-0">
                <div data-v-d90ff256="" className="flex items-center justify-between mb-2">
                  <p data-v-d90ff256="" className={MINI_TITLE}>
                    {t('extraction.testInput')}
                  </p>
                  <span data-v-d90ff256="" className={MINI_META}>
                    {sample.length}/{MAX_INPUT}
                  </span>
                </div>
                <textarea
                  data-v-d90ff256=""
                  value={sample}
                  maxLength={MAX_INPUT}
                  onChange={(e) => setSample(e.target.value)}
                  placeholder={t('extraction.debugInput')}
                  className={DEBUG_INPUT}
                />
              </div>

              <div data-v-d90ff256="" className="flex flex-col flex-1 border-t border-[#F1F5F9] min-h-0">
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
                      <div key={i} className="rounded-md border border-[#E2E8F0] bg-[#F8FAFC] px-3.5 py-3 text-[13px] leading-6">
                        {r.type && (
                          <span className="mr-2 rounded-[6px] border border-[#c7c9f7] bg-[#eef0ff] px-2 py-0.5 font-mono text-xs text-primary">
                            {r.type}
                          </span>
                        )}
                        <span className="text-second-gray">{r.content}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div data-v-d90ff256="" className="flex-1 flex flex-col items-center justify-center px-6 text-center">
                    <Icon name="i-lucide:file-search" className="mb-2.5 h-7 w-7 text-[#CBD5E1]" />
                    <div data-v-d90ff256="" className="text-xs text-third-gray">
                      {results ? t('common.empty') : t('extraction.resultEmpty')}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
