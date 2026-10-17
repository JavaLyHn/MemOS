import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { AccessMethodHint } from '../components/AccessMethodHint'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { useLang, useT, useToast, useMeta, useProject } from '../lib/store'
import { buildTabs, tabLabel, type Step } from '../lib/quickstart-data'

const Q = { 'data-v-de9e37d2': '' } as const
const T = { 'data-v-1bbcdca4': '' } as const
const S = { 'data-v-82f9e747': '' } as const
const C = { 'data-v-ce54f47b': '' } as const
const N = { 'data-v-36c1fd29': '' } as const
const B = { 'data-v-e281b1a5': '' } as const

const SUBTAB =
  'inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors py-1.5 gap-1.5 text-default hover:bg-elevated active:bg-elevated focus:outline-none focus-visible:bg-elevated hover:disabled:bg-transparent dark:hover:disabled:bg-transparent hover:aria-disabled:bg-transparent dark:hover:aria-disabled:bg-transparent min-h-9 rounded-lg px-4 text-sm font-medium shadow-none quickstart-subtab'

const SUBTAB_ACTIVE =
  'inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors py-1.5 gap-1.5 text-primary bg-primary/10 hover:bg-primary/15 active:bg-primary/15 focus:outline-none focus-visible:bg-primary/15 disabled:bg-primary/10 aria-disabled:bg-primary/10 min-h-9 rounded-lg px-4 text-sm font-medium shadow-none quickstart-subtab'

const PILL_LINK =
  'inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors py-1.5 gap-1.5 focus:outline-none focus-visible:bg-primary/10 disabled:bg-transparent aria-disabled:bg-transparent dark:disabled:bg-transparent dark:aria-disabled:bg-transparent cursor-pointer whitespace-nowrap rounded-md min-h-8 px-2 text-sm font-medium text-primary hover:bg-primary/5 active:bg-primary/5 shadow-none'

const PILL_OUTLINE =
  'rounded-md font-medium inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors px-2.5 py-1.5 text-xs gap-1.5 ring ring-inset ring-primary/50 text-primary hover:bg-primary/10 active:bg-primary/10 disabled:bg-transparent aria-disabled:bg-transparent'

const COPY_BTN =
  'rounded-md font-medium inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors text-xs gap-1 text-default hover:bg-elevated active:bg-elevated focus:outline-none focus-visible:bg-elevated hover:disabled:bg-transparent dark:hover:disabled:bg-transparent hover:aria-disabled:bg-transparent dark:aria-disabled:bg-transparent p-1'

function CodeBlock({ step }: { step: Step }) {
  const t = useT()
  const toast = useToast()
  return (
    <div {...S} className="setup-timeline-step__code-shell rounded-lg overflow-hidden" style={{ border: '1px solid rgb(226, 232, 240)' }}>
      <div {...S} className={`code-area${step.multiline ? ' code-area--multiline' : ''}`}>
        <div {...S} className="code-area__body">
          {step.multiline ? (
            <pre {...S} className="normal-code">
              {step.code}
            </pre>
          ) : (
            <code {...S} className="api-key-code">
              {step.code}
            </code>
          )}
        </div>
        <span {...C} {...S} className="base-copyable-wrapper shrink-0">
          <button
            type="button"
            aria-label={t('quickstart.copyStep')}
            className={COPY_BTN}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(step.code)
                toast(t('common.copied'))
              } catch {
                toast(t('common.failed'), 'err')
              }
            }}
          >
            <Icon name="i-lucide:copy" className="shrink-0 size-4" />
          </button>
        </span>
      </div>
    </div>
  )
}

/** 一个步骤卡片。标题那行是折叠开关，折叠时卡片多一个 --collapsed 类、箭头换成向下 */
function TimelineStep({ step, lang }: { step: Step; lang: 'zh' | 'en' }) {
  const [collapsed, setCollapsed] = useState(false)
  const bodyId = `setup-step-body-${step.n}`
  const descId = `setup-step-desc-${step.n}`
  return (
    <div {...S} className="setup-timeline-step">
      <div
        {...S}
        className={`setup-timeline-step__card${step.desc ? ' setup-timeline-step__card--with-desc' : ''}${
          collapsed ? ' setup-timeline-step__card--collapsed' : ''
        }`}
      >
        <div {...S} className="step-index-badge">
          <span {...S} className="step-index-badge__num">
            {step.n}
          </span>
        </div>
        <button
          {...S}
          type="button"
          className="step-fold-header min-h-6 min-w-0"
          aria-expanded={!collapsed}
          aria-controls={bodyId}
          aria-describedby={step.desc ? descId : undefined}
          onClick={() => setCollapsed((c) => !c)}
        >
          <h3 {...S} className="step-fold-title text-sm font-semibold text-gray-900 mb-0 min-w-0 text-left">
            {step.title[lang]}
          </h3>
          <Icon {...S} name={collapsed ? 'i-lucide:chevron-down' : 'i-lucide:chevron-up'} className="step-fold-chevron shrink-0" />
        </button>
        {step.desc && (
          <span {...S} id={descId} className="step-fold-desc text-xs text-[#62748E] leading-relaxed whitespace-pre-line">
            {step.desc[lang]}
          </span>
        )}
        <div
          {...S}
          id={bodyId}
          className={`step-fold-body${step.desc ? ' step-fold-body--after-desc' : ''}`}
          style={collapsed ? { display: 'none' } : undefined}
        >
          <CodeBlock step={step} />
        </div>
      </div>
    </div>
  )
}

export function QuickStart() {
  const t = useT()
  const { lang } = useLang()
  const toast = useToast()
  const [card, setCard] = useState<'agent' | 'code'>('agent')
  const [tabId, setTabId] = useState('mcp')
  const [tipOpen, setTipOpen] = useState(true)

  const { currentProjectId } = useProject()
  const { data } = useAsync(
    () => (currentProjectId ? api.keys.list(currentProjectId, 1, 1) : Promise.resolve({ records: [], total: 0 })),
    [currentProjectId],
  )
  const apiKey = data?.records[0]?.apiKey ?? ''
  const { tools } = useMeta()

  const tabs = useMemo(() => buildTabs(apiKey, { tools }), [apiKey, tools])
  const visible = tabs.filter((x) => x.card === card)
  const tab = visible.find((x) => x.id === tabId) ?? visible[0]

  const pickCard = (c: 'agent' | 'code') => {
    setCard(c)
    const first = tabs.find((x) => x.card === c)
    if (first) setTabId(first.id)
  }

  return (
    <>
      <div {...Q} className="quickstart-focus-column">
        <div {...Q} className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex min-w-0 items-end gap-2">
              <h2 className="text-lg text-[#303133] font-semibold leading-6.25">{t('quickstart.title')}</h2>
              <p className="text-sm text-[#606266] leading-5.5">{t('quickstart.subtitle')}</p>
            </div>
          </div>
        </div>

        {tipOpen && (
          <div {...T} {...Q} className="quickstart-tip-bar mb-5">
            <div {...T} className="quickstart-tip-bar__content">
              <img {...T} src="/icons/quickstart-tip.svg" className="quickstart-tip-bar__icon" alt="" />
              <p {...T} className="quickstart-tip-bar__text">
                {t('quickstart.tip')}
              </p>
            </div>
            <div {...T} className="quickstart-tip-bar__actions">
              <Link to="/cn/usage" className={PILL_LINK}>
                {t('quickstart.tipCta')}
                <Icon name="i-lucide:rocket" className="shrink-0 size-4 w-4 h-4" />
              </Link>
              <button
                {...T}
                type="button"
                aria-label={t('quickstart.tipClose')}
                className="quickstart-tip-bar__close"
                onClick={() => setTipOpen(false)}
              >
                <Icon {...T} name="i-lucide:x" className="quickstart-tip-bar__close-icon" />
              </button>
            </div>
          </div>
        )}

        <div {...Q} className="category-cards mb-8">
          <button
            {...Q}
            type="button"
            className={`pick-card${card === 'agent' ? ' pick-card--selected' : ''}`}
            onClick={() => pickCard('agent')}
          >
            <span {...Q} className="pick-card__icon-box">
              <img {...Q} src="/icons/agent-logo.svg" className="pick-card__icon" alt="" />
            </span>
            <div {...Q} className="pick-card__texts">
              <span {...Q} className="pick-card__title">
                {t('quickstart.card.agent')}
              </span>
              <p {...Q} className="pick-card__desc">
                {t('quickstart.card.agentDesc')}
              </p>
            </div>
          </button>
          <button
            {...Q}
            type="button"
            className={`pick-card${card === 'code' ? ' pick-card--selected' : ''}`}
            onClick={() => pickCard('code')}
          >
            <span {...Q} className="pick-card__icon-box">
              <Icon {...Q} name="i-lucide:code" className="pick-card__icon" />
            </span>
            <div {...Q} className="pick-card__texts">
              <span {...Q} className="pick-card__title">
                {t('quickstart.card.code')}
              </span>
              <p {...Q} className="pick-card__desc">
                {t('quickstart.card.codeDesc')}
              </p>
            </div>
          </button>
        </div>

        <div {...Q} className="quickstart-subtabs-row">
          <div {...Q} className="quickstart-subtabs">
            {visible.map((x) => (
              <button key={x.id} type="button" className={x.id === tab.id ? SUBTAB_ACTIVE : SUBTAB} onClick={() => setTabId(x.id)}>
                <Icon name={x.icon} className="size-4 shrink-0" />
                {tabLabel(x, lang)}
              </button>
            ))}
          </div>
          <AccessMethodHint text={t('quickstart.hint')} />
        </div>
      </div>

      <div {...Q} className="setup-steps-block">
        {!apiKey && (
          <div {...Q} className="mb-4 text-sm text-[#c2410c]">
            {t('quickstart.noKey')}{' '}
            <Link to="/cn/apikeys" className="text-[#4044ed] hover:underline">
              {t('quickstart.gotoKeys')}
            </Link>
          </div>
        )}

        {tab.prompt ? (
          <div {...Q} className="quick-access-block quick-access-block--static">
            <div {...Q} className="quick-access-header">
              <h4 {...Q} className="quick-access-title">
                {t('quickstart.copyPrompt')}
              </h4>
              <p {...Q} className="quick-access-desc">
                {t('quickstart.subtitle')}
              </p>
            </div>
            <div {...Q} className="quick-access-actions">
              <button
                type="button"
                className={PILL_OUTLINE}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(tab.prompt![lang])
                    toast(t('common.copied'))
                  } catch {
                    toast(t('common.failed'), 'err')
                  }
                }}
              >
                <Icon name="i-lucide:copy" className="shrink-0 size-4" />
                {t('quickstart.copyPrompt')}
              </button>
            </div>
            <div {...Q} className="quick-access-prompt-preview">
              <pre>{tab.prompt[lang]}</pre>
            </div>
          </div>
        ) : (
          <>
            <div {...Q} className="setup-section-head">
              <h3 {...Q} className="setup-section-head__title">
                {tab.head[lang]}
              </h3>
              <div {...Q} className="setup-section-head__actions">
                <Link {...Q} to={tab.docs} className="setup-docs-link">
                  {t('quickstart.docs')}
                  <Icon {...Q} name="i-lucide:arrow-up-right" className="setup-docs-link__icon" />
                </Link>
              </div>
            </div>

            <div {...S} className="flex flex-col space-y-8 mb-6">
              <div {...S} className="flex-1 w-full">
                <div {...S}>
                  <div {...S} className="setup-timeline-steps setup-timeline-steps--quickstart">
                    {tab.steps.map((step) => (
                      <TimelineStep key={step.n} step={step} lang={lang} />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {tab.id === 'mcp' && (
          <div {...N} {...Q} className="mcp-try-note mb-5 mt-5">
            <div {...B} {...N} className="try-note-block">
              <p {...B} className="try-note__intro">
                {t('quickstart.tryIntro')}
              </p>
              <ul {...B} className="try-note__list">
                <li {...B}>
                  <span {...B} className="try-note__label">
                    {t('quickstart.tryLabel1')}
                  </span>
                  <span {...B} className="try-note__content">
                    {t('quickstart.tryContent1')}
                  </span>
                </li>
                <li {...B}>
                  <span {...B} className="try-note__label">
                    {t('quickstart.tryLabel2')}
                  </span>
                  <span {...B} className="try-note__content">
                    {t('quickstart.tryContent2')}
                  </span>
                </li>
              </ul>
              <p {...B} className="try-note__outro">
                {t('quickstart.tryOutro')}
              </p>
            </div>
          </div>
        )}
      </div>
    </>
  )
}
