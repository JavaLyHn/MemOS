/** 属性树模板的新建 / 详情，两页共用一张表单卡片。类名逐字取自设计稿 */

import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { Icon } from '../components/Icon'
import { useAsync } from '../lib/useAsync'
import { useProject, useT, useToast } from '../lib/store'
import { BTN_BACK, BTN_PRIMARY, BTN_RESET, DIALOG_INPUT, FORM_CARD, FORM_LABEL, JSON_BOX, JSON_PRE, JSON_TEXTAREA } from '../lib/cls'

/** 「重置为默认配置」恢复的就是这份结构 */
const DEFAULT_STRUCTURE = `{
  "基础信息": {
    "姓名": {
      "value": "",
      "algorithm_updatable": false
    },
    "职业": {
      "value": "",
      "algorithm_updatable": true
    },
    "居住地": {
      "value": "",
      "algorithm_updatable": true
    }
  },
  "性格标签": {
    "最大优点": {
      "value": "",
      "algorithm_updatable": true
    },
    "最大弱点": {
      "value": "",
      "algorithm_updatable": true
    }
  },
  "互动偏好": {
    "安慰方式": {
      "value": "",
      "algorithm_updatable": true
    },
    "决策偏好": {
      "value": "",
      "algorithm_updatable": true
    },
    "雷点": {
      "value": "",
      "algorithm_updatable": true
    }
  }
}`

/** 必填星号是独立的 <span>，不是 label 的伪元素 */
function Req() {
  return <span className="text-red-500">*</span>
}

/** 带返回箭头 + 标题 + 描述的页头，详情页用它 */
function DetailHeader({ title, desc, backTo }: { title: string; desc?: string; backTo: string }) {
  const t = useT()
  return (
    <div className="flex justify-between items-center mb-4">
      <div className="flex items-center gap-2 min-w-0">
        <Link to={backTo} aria-label={t('profile.new.back')} className={BTN_BACK}>
          <Icon name="i-lucide:arrow-left" className="shrink-0 size-4" />
        </Link>
        <div className="flex min-w-0 items-end gap-2">
          <h2 className="text-lg text-[#303133] font-semibold leading-6.25">{title}</h2>
          {desc && <p className="text-sm text-[#606266] leading-5.5">{desc}</p>}
        </div>
      </div>
    </div>
  )
}

function FormCard({ footer, children }: { footer?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col flex-1 min-h-0 gap-4 overflow-hidden">
      <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
        <div className={FORM_CARD}>
          {children}
          {footer && <div className="shrink-0 mt-4 pt-4 border-t border-[#E2E8F0] flex items-center justify-end gap-2">{footer}</div>}
        </div>
      </div>
    </div>
  )
}

export function ProfileTemplateNew() {
  const t = useT()
  const toast = useToast()
  const nav = useNavigate()
  const { currentProjectId } = useProject()
  const [name, setName] = useState('')
  const [structure, setStructure] = useState(DEFAULT_STRUCTURE)
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (busy) return
    if (!name.trim()) {
      toast(t('profile.new.needName'), 'err')
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(structure)
    } catch {
      toast(t('profile.new.badJson'), 'err')
      return
    }
    setBusy(true)
    try {
      await api.profileTemplate.create({ projectId: currentProjectId, name: name.trim(), structure: parsed })
      toast(t('profile.new.created'))
      nav('/cn/profileTemplate')
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), 'err')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <DetailHeader title={t('profile.new.title')} backTo="/cn/profileTemplate" />
      <FormCard
        footer={
          <button type="button" className={BTN_PRIMARY} disabled={busy} onClick={submit}>
            {t('profile.new.submit')}
          </button>
        }
      >
        <div className="mb-4 shrink-0 flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <label className={`${FORM_LABEL} mb-1.5`}>
              {t('profile.new.name')} <Req />
            </label>
            <div className="relative inline-flex items-center w-full">
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t('profile.new.namePlaceholder')}
                className={DIALOG_INPUT}
              />
            </div>
          </div>
        </div>

        <div className="flex flex-col flex-1 min-h-0">
          <div className="shrink-0 flex items-center justify-between gap-3 mb-1.5">
            <label className={FORM_LABEL}>
              {t('profile.new.structure')} <Req />
            </label>
            <button type="button" className={BTN_RESET} onClick={() => setStructure(DEFAULT_STRUCTURE)}>
              <Icon name="i-lucide:rotate-ccw" className="shrink-0 size-4" />
              {t('profile.new.reset')}
            </button>
          </div>
          <div className={JSON_BOX}>
            <div className="relative inline-flex items-center w-full h-full">
              <textarea
                rows={24}
                value={structure}
                onChange={(e) => setStructure(e.target.value)}
                placeholder={t('profile.new.structurePlaceholder')}
                className={JSON_TEXTAREA}
              />
            </div>
          </div>
        </div>
      </FormCard>
    </>
  )
}

/** 结构存成字符串还是对象不确定，两种都兜住 */
function asJsonText(v: unknown): string {
  if (v == null || v === '') return ''
  if (typeof v === 'string') {
    try {
      return JSON.stringify(JSON.parse(v), null, 2)
    } catch {
      return v
    }
  }
  return JSON.stringify(v, null, 2)
}

/** 结构之外的管理字段。接口既可能把结构单独放一个键，也可能平铺在同一层，两种都要认 */
const META_KEYS = new Set(['id', 'templateId', 'templateName', 'projectId', 'bindingCount', 'updatedAt', 'createdAt'])

function pickStructure(raw: Record<string, unknown>): unknown {
  const direct = raw.structure ?? raw.templateStructure ?? raw.templateMetadata ?? raw.metadata
  if (direct != null) return direct
  const rest = Object.fromEntries(Object.entries(raw).filter(([k]) => !META_KEYS.has(k)))
  return Object.keys(rest).length ? rest : undefined
}

export function ProfileTemplateDetail() {
  const t = useT()
  const { currentProjectId } = useProject()
  const { templateId = '' } = useParams()

  const { data, state, error } = useAsync(() => api.profileTemplate.detail(templateId, currentProjectId), [templateId, currentProjectId])

  const raw: Record<string, unknown> = data ?? {}
  const structure = pickStructure(raw)
  const bindingCount = typeof raw.bindingCount === 'number' ? raw.bindingCount : 0
  const updatedAt = typeof raw.updatedAt === 'string' && raw.updatedAt ? raw.updatedAt : '-'
  const templateName = typeof raw.templateName === 'string' && raw.templateName ? raw.templateName : '-'

  return (
    <>
      <DetailHeader title={t('profile.detail.title')} desc={t('profile.detail.desc')} backTo="/cn/profileTemplate" />

      <div className="flex flex-col flex-1 min-h-0 gap-4 overflow-hidden">
        <div className="shrink-0 grid grid-cols-1 md:grid-cols-3 gap-4 rounded-lg border border-[#E2E8F0] bg-white px-5 py-4">
          <div className="min-w-0">
            <div className="text-xs text-third-gray mb-1">{t('profile.detail.templateId')}</div>
            <div className="text-sm font-mono text-second-gray break-all">{templateId}</div>
          </div>
          <div className="min-w-0">
            <div className="text-xs text-third-gray mb-1">{t('profile.detail.bindingCount')}</div>
            <div className="text-sm text-second-gray">{bindingCount}</div>
          </div>
          <div className="min-w-0">
            <div className="text-xs text-third-gray mb-1">{t('profile.detail.updatedAt')}</div>
            <div className="text-sm text-second-gray">{updatedAt}</div>
          </div>
        </div>

        <FormCard>
          <div className="mb-4 shrink-0 flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <label className={`${FORM_LABEL} mb-1.5`}>{t('profile.new.name')}</label>
              <div className="text-sm text-second-gray leading-9 break-all">{templateName}</div>
            </div>
          </div>
          <div className="flex flex-col flex-1 min-h-0">
            <div className="shrink-0 flex items-center justify-between gap-3 mb-1.5">
              <label className={FORM_LABEL}>{t('profile.new.structure')}</label>
            </div>
            <div className={JSON_BOX}>
              <pre className={JSON_PRE}>
                {state === 'loading' && !data
                  ? t('common.loading')
                  : state === 'error' && !data
                    ? `${t('common.failed')}：${error ?? ''}`
                    : asJsonText(structure)}
              </pre>
            </div>
          </div>
        </FormCard>
      </div>
    </>
  )
}
