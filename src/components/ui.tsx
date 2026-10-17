/** 共用组件。表格与分页的类名逐字取自设计稿，勿随意增删。 */

import type { ReactNode } from 'react'
import { Icon } from './Icon'
import { BTN_DIALOG_CLOSE, BTN_PAGE_ACTIVE, BTN_PAGER, BTN_PRIMARY, BTN_TEXT_LINK } from '../lib/cls'
import { useT } from '../lib/store'

/** 标签的展示色。成功 / 失败两种，另留一档中性色 */
export type Tone = 'ok' | 'warn' | 'default'

/** 表格所在页面的作用域属性，表格样式挂在这个属性下 */
export const T = { 'data-v-13b6c0ea': '' } as const

export const TH =
  'px-4 py-3.5 text-sm text-left rtl:text-right [&:has([role=checkbox])]:pe-0 text-second-gray font-normal red-header-[#E2E8F0]'

/** 表格 td 基类，默认不换行；需要折行的列自己追加 break-all */
export const TD = 'p-4 text-sm whitespace-nowrap [&:has([role=checkbox])]:pe-0 py-3 text-second-gray leading-5'

/** 允许折行的 td（长文本列用）。两个类在 CSS 里的先后决定胜负 */
export const TD_BREAK = `${TD} whitespace-break-spaces break-all`

export function PageHeader({ title, desc, actions }: { title: string; desc?: string; actions?: ReactNode }) {
  return (
    <div className="flex justify-between items-center mb-4">
      <div className="flex items-center gap-2 min-w-0">
        <div className="flex min-w-0 items-end gap-2">
          <h2 className="text-lg text-[#303133] font-semibold leading-6.25">{title}</h2>
          {desc && <p className="text-sm text-[#606266] leading-5.5">{desc}</p>}
        </div>
      </div>
      {actions && (
        <div>
          <div className="flex items-center gap-3">{actions}</div>
        </div>
      )}
    </div>
  )
}

/** 表格外框。只有「调用日志」页加高度上限，其余页不限高 */
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div {...T} className={`relative overflow-auto border-1 border-[#E2E8F0] rounded-[12px] bg-white ${className}`}>
      {children}
    </div>
  )
}

export function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <table className="min-w-full overflow-clip">
      <thead className="sticky top-0 inset-x-0 z-[1] backdrop-blur-none bg-default">
        <tr className="data-[selected=true]:bg-elevated/50">{head}</tr>
        <tr className="absolute z-[1] left-0 w-full h-px bg-(--ui-border-accented)" />
      </thead>
      <tbody className="divide-y divide-default [&>tr]:cursor-pointer [&>tr]:data-[selectable=true]:hover:bg-elevated/50 [&>tr]:data-[selectable=true]:focus-visible:outline-primary">
        {children}
      </tbody>
    </table>
  )
}

export function Th({ children }: { children: ReactNode }) {
  return (
    <th data-pinned="false" scope="col" className={TH}>
      {children}
    </th>
  )
}

/** 加载 / 空 / 出错三种状态的整行占位 */
export function StateRow({ colSpan, state, error }: { colSpan: number; state: 'loading' | 'ready' | 'error'; error?: string }) {
  const t = useT()
  if (state === 'ready') {
    return (
      <tr>
        <td colSpan={colSpan} className="py-6 text-center text-sm text-muted">
          No data
        </td>
      </tr>
    )
  }
  const text = state === 'loading' ? t('common.loading') : `${t('common.failed')}：${error ?? ''}`
  return (
    <tr>
      <td colSpan={colSpan} className="py-6 text-center text-sm text-muted">
        {text}
      </td>
    </tr>
  )
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const t = useT()
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const btn = (label: string, icon: string, target: number, disabled: boolean) => (
    <button type="button" disabled={disabled} aria-label={label} className={BTN_PAGER} onClick={() => onPage(target)}>
      <Icon name={icon} className="shrink-0 size-5" />
    </button>
  )
  return (
    <div {...T} className="flex justify-between items-center pt-4">
      <div {...T} />
      <nav {...T}>
        <div className="flex items-center gap-1">
          {btn(t('common.firstPage'), 'i-lucide:chevrons-left', 1, page <= 1)}
          {btn(t('common.prevPage'), 'i-lucide:chevron-left', page - 1, page <= 1)}
          <button type="button" data-type="page" aria-current="page" data-selected="true" className={BTN_PAGE_ACTIVE}>
            <span className="truncate min-w-5 text-center">{page}</span>
          </button>
          {btn(t('common.nextPage'), 'i-lucide:chevron-right', page + 1, page >= pages)}
          {btn(t('common.lastPage'), 'i-lucide:chevrons-right', pages, page >= pages)}
        </div>
      </nav>
    </div>
  )
}

/** 对话框。遮罩 fade-in、面板 scale-in，各 200ms */
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  if (!open) return null
  return (
    <>
      <div
        data-state="open"
        onClick={onClose}
        className="fixed inset-0 bg-overlay data-[state=open]:animate-[fade-in_200ms_ease-out] data-[state=closed]:animate-[fade-out_200ms_ease-in]"
      />
      <div
        role="dialog"
        data-state="open"
        className="fixed bg-default divide-y divide-default flex flex-col focus:outline-none data-[state=open]:animate-[scale-in_200ms_ease-out] data-[state=closed]:animate-[scale-out_200ms_ease-in] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[calc(100vw-2rem)] max-w-lg max-h-[calc(100dvh-2rem)] sm:max-h-[calc(100dvh-4rem)] shadow-lg ring ring-default overflow-hidden rounded-[12px]"
      >
        <div className="flex items-center gap-1.5 p-4 sm:px-6 min-h-16 border-b-0 pt-5 pb-6 text-lg leading-6.25">
          <div>
            <h2 className="text-highlighted font-semibold">{title}</h2>
          </div>
          <button type="button" aria-label="Close" className={BTN_DIALOG_CLOSE} onClick={onClose}>
            <Icon name="i-lucide:x" className="shrink-0 size-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 pt-0! border-[#E2E8F0]">{children}</div>
        {footer && <div className="flex items-center p-4 sm:px-6 gap-2">{footer}</div>}
      </div>
    </>
  )
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
  icon,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  icon?: string
}) {
  return (
    <button type="button" className={BTN_PRIMARY} onClick={onClick} disabled={disabled}>
      {icon && <Icon name={icon} className="shrink-0 size-5" />}
      {children}
    </button>
  )
}

export function TextLinkButton({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <button type="button" className={BTN_TEXT_LINK} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  )
}

export function SearchBox({
  value,
  onChange,
  onSubmit,
  onFilter,
  filterOpen = false,
  filter,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onFilter?: () => void
  filterOpen?: boolean
  filter?: ReactNode
  /** 各页的提示语不一样，由调用方传入 */
  placeholder?: string
}) {
  const t = useT()
  return (
    <>
      <div className="relative inline-flex items-center w-64">
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSubmit()}
          placeholder={placeholder ?? t('common.searchPlaceholder')}
          className="w-full rounded-md border-0 appearance-none placeholder:text-dimmed focus:outline-none disabled:cursor-not-allowed disabled:opacity-75 transition-colors px-2.5 py-1.5 text-sm gap-1.5 text-highlighted bg-default ring ring-inset ring-accented focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary ps-9"
        />
        <span className="absolute inset-y-0 start-0 flex items-center ps-2.5">
          <Icon name="i-lucide:search" className="shrink-0 text-dimmed size-5" />
        </span>
      </div>
      {onFilter && (
        <div className="relative">
          <button type="button" aria-expanded={filterOpen} className={BTN_PAGER} onClick={onFilter}>
            <Icon name="i-db-filter-line" className="shrink-0 size-5" />
          </button>
          {filterOpen && filter}
        </div>
      )}
    </>
  )
}

export function Tag({ text, tone = 'default' }: { text: string; tone?: Tone }) {
  const cls =
    tone === 'ok'
      ? 'bg-[#ecfdf5] text-[#047857] border-[#a7f3d0]'
      : tone === 'warn'
        ? 'bg-[#fff7ed] text-[#c2410c] border-[#fed7aa]'
        : 'bg-[#f7f8fb] text-[#475569] border-[#e2e8f0]'
  return <span className={`inline-flex items-center rounded-[6px] border px-2 py-0.5 text-xs leading-5 ${cls}`}>{text}</span>
}
