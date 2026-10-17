/** 列表页筛选浮层。这一块用的是 Tailwind 原生色系，
 *  跟页面主体的语义 token 不是一套，别顺手统一。 */

import type { ReactNode } from 'react'
import { Icon } from './Icon'
import { BTN_FILTER, BTN_FILTER_RESET, FILTER_DATERANGE, FILTER_INPUT, FILTER_LABEL, FILTER_SELECT } from '../lib/cls'
import { useT } from '../lib/store'

/** 浮层本体。定位由外层的 relative 容器负责 */
export function FilterPopover({
  open,
  onFilter,
  onReset,
  children,
}: {
  open: boolean
  onFilter: () => void
  onReset: () => void
  children: ReactNode
}) {
  const t = useT()
  if (!open) return null
  return (
    <div className="absolute top-full right-0 mt-2 w-[400px] bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-4 z-[10000]">
      {children}
      <div className="flex justify-between dark:border-gray-700">
        <div className="flex gap-2">
          <button type="button" className={BTN_FILTER} onClick={onFilter}>
            {t('filter.apply')}
          </button>
          <button type="button" className={BTN_FILTER_RESET} onClick={onReset}>
            {t('filter.reset')}
          </button>
        </div>
      </div>
    </div>
  )
}

/** 一个字段：标签 + 控件 */
export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-[20px]">
      <label className={FILTER_LABEL}>{label}</label>
      {children}
    </div>
  )
}

/** 两列排布的字段行 */
export function FilterFieldRow({ children }: { children: ReactNode }) {
  return <div className="mb-[20px] grid grid-cols-2 gap-3">{children}</div>
}

/** 下拉选择。交互用一层透明的原生 select 顶在触发器上 */
export function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder: string
}) {
  const current = options.find((o) => o.value === value)
  return (
    <button type="button" className={FILTER_SELECT}>
      <span className={`truncate pointer-events-none ${current ? '' : 'text-dimmed'}`}>{current ? current.label : placeholder}</span>
      <span className="absolute inset-y-0 end-0 flex items-center pe-2.5">
        <Icon name="i-lucide:chevron-down" className="shrink-0 text-dimmed size-5" />
      </span>
      <select
        className="absolute inset-0 w-full h-full cursor-pointer opacity-0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={placeholder}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </button>
  )
}

/** 文本输入 */
export function FilterInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div className="relative inline-flex items-center w-full">
      <input className={FILTER_INPUT} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </div>
  )
}

/** 日期区间。原生 datetime-local 不吃 placeholder，
 *  所以让它透明铺满，显示的文案由上面那层 span 负责。 */
export function FilterDateRange({ start, end, onChange }: { start: string; end: string; onChange: (start: string, end: string) => void }) {
  const t = useT()
  const fmt = (v: string) => v.replace('T', ' ')
  const slot = (value: string, placeholder: string, onPick: (v: string) => void) => (
    <div className="flex-1 min-w-0 text-center relative">
      <span className={`text-sm leading-none ${value ? 'text-highlighted' : 'text-dimmed'}`}>{value ? fmt(value) : placeholder}</span>
      <input
        type="datetime-local"
        value={value}
        onChange={(e) => onPick(e.target.value)}
        className="absolute inset-0 w-full h-full cursor-pointer opacity-0"
        aria-label={placeholder}
      />
    </div>
  )
  return (
    <div className="w-full group relative inline-flex items-center">
      <div className={FILTER_DATERANGE}>
        <Icon name="i-lucide:calendar" className="size-5 text-dimmed shrink-0" />
        {slot(start, t('filter.startTime'), (v) => onChange(v, end))}
        <span className="text-dimmed text-sm leading-none shrink-0">{t('filter.to')}</span>
        {slot(end, t('filter.endTime'), (v) => onChange(start, v))}
      </div>
    </div>
  )
}
