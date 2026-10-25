import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../components/Icon'
import { AccessMethodHint } from '../components/AccessMethodHint'
import { CopyButton } from '../components/ui/copy-button'
import { useLang, useT, useToast, useMeta } from '../lib/store'
import { copyText } from '../lib/clipboard'
import { HINT_COPY, buildTabs, tabLabel, type Step } from '../lib/quickstart-data'

const Q = { 'data-v-de9e37d2': '' } as const
const S = { 'data-v-82f9e747': '' } as const
const N = { 'data-v-36c1fd29': '' } as const
const B = { 'data-v-e281b1a5': '' } as const

const SUBTAB =
  'inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors py-1.5 gap-1.5 text-default hover:bg-elevated active:bg-elevated focus:outline-none focus-visible:bg-elevated hover:disabled:bg-transparent dark:hover:disabled:bg-transparent hover:aria-disabled:bg-transparent dark:hover:aria-disabled:bg-transparent min-h-9 rounded-lg px-4 text-sm font-medium shadow-none quickstart-subtab'

const SUBTAB_ACTIVE =
  'inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors py-1.5 gap-1.5 text-primary bg-primary/10 hover:bg-primary/15 active:bg-primary/15 focus:outline-none focus-visible:bg-primary/15 disabled:bg-primary/10 aria-disabled:bg-primary/10 min-h-9 rounded-lg px-4 text-sm font-medium shadow-none quickstart-subtab'

const PILL_OUTLINE =
  'rounded-md font-medium inline-flex items-center disabled:cursor-not-allowed aria-disabled:cursor-not-allowed disabled:opacity-75 aria-disabled:opacity-75 transition-colors px-2.5 py-1.5 text-xs gap-1.5 ring ring-inset ring-primary/50 text-primary hover:bg-primary/10 active:bg-primary/10 disabled:bg-transparent aria-disabled:bg-transparent'

function CodeBlock({ step }: { step: Step }) {
  const t = useT()
  const { lang } = useLang()
  // 「获取 API Key」这类步骤在控制台里有对应页面，渲染成一个跳转按钮：
  // 放一段代码（哪怕是占位符）也帮不上忙，人需要的是那把钥匙本身。
  if (step.link) {
    return (
      <div {...S} className="setup-timeline-step__code-shell rounded-lg overflow-hidden" style={{ border: '1px solid rgb(226, 232, 240)' }}>
        <div {...S} className="code-area">
          <div {...S} className="code-area__body items-center">
            <Link to={step.link.to} className="api-key-code text-primary hover:underline">
              {step.link.label[lang]}
            </Link>
          </div>
        </div>
      </div>
    )
  }
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
        <CopyButton text={step.code} label={t('quickstart.copyStep')} className="absolute right-2 top-2" />
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
          <h3 {...S} className="step-fold-title text-sm font-semibold text-ink mb-0 min-w-0 text-left">
            {step.title[lang]}
          </h3>
          <Icon {...S} name={collapsed ? 'i-lucide:chevron-down' : 'i-lucide:chevron-up'} className="step-fold-chevron shrink-0" />
        </button>
        {step.desc && (
          <span {...S} id={descId} className="step-fold-desc text-xs text-ink-muted leading-relaxed whitespace-pre-line">
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
  const [tabId, setTabId] = useState('mcp')

  // ⚠️ 这里原来会把当前项目的第一把密钥查出来、嵌进所有示例代码里。
  //    现在示例里只有占位符，页面不需要也不应该拿到任何密钥（见 quickstart-data.ts）。
  const { tools } = useMeta()

  const tabs = useMemo(() => buildTabs({ tools }), [tools])
  const tab = tabs.find((x) => x.id === tabId) ?? tabs[0]

  /** 「选择哪种接入方式？」浮层里的行。
   *
   *  ⚠️ 方式名取自**页签自己的 label**，行数也就是页签数——不在这里另写一份。
   *  这里原来写死了 `Plugin / CLI + Skill / MCP` 三行，而页签里一个都没有。 */
  const hintRows = useMemo(
    () => tabs.map((x) => [tabLabel(x, lang), t(HINT_COPY[x.id].scene), t(HINT_COPY[x.id].feature)] as [string, string, string]),
    [tabs, lang, t],
  )

  return (
    <>
      <div {...Q} className="quickstart-focus-column">
        <div {...Q} className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex min-w-0 items-end gap-2">
              <h2 className="text-lg text-ink font-semibold leading-6.25">{t('quickstart.title')}</h2>
              <p className="text-sm text-ink-secondary leading-5.5">{t('quickstart.subtitle')}</p>
            </div>
          </div>
        </div>

        {/* 这里原来有一条「我们向每位开发者赠送百万级免费 token…」的宣传条。
            2026-10-19 用户要求删掉：它是**宣传**，而且对「百度厂内版」来说根本不存在
            这回事——写一句做不到的承诺比不写更糟。 */}

        {/* 这里原来有两张卡片（「Agent 接入」/「代码集成」）当第一层选择器。
            2026-10-19 用户逐条点掉之后只剩 MCP / Hermes / 让 Agent 自己配三种，
            全在 agent 一侧——「代码集成」那张卡片会变成空的，点进去没有任何内容；
            只剩一张卡片则是个点了不产生任何变化的死控件（`AGENTS.md` 第八节）。
            所以整行去掉，页签直接当第一层选择器。 */}

        <div {...Q} className="quickstart-subtabs-row">
          <div {...Q} className="quickstart-subtabs">
            {tabs.map((x) => (
              <button key={x.id} type="button" className={x.id === tab.id ? SUBTAB_ACTIVE : SUBTAB} onClick={() => setTabId(x.id)}>
                <Icon name={x.icon} className="size-4 shrink-0" />
                {tabLabel(x, lang)}
              </button>
            ))}
          </div>
          <AccessMethodHint text={t('quickstart.hint')} rows={hintRows} />
        </div>
      </div>

      <div {...Q} className="setup-steps-block">
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
                    await copyText(tab.prompt![lang])
                    toast(t('common.copied'))
                  } catch {
                    toast(t('common.copyFailed'), 'err')
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
