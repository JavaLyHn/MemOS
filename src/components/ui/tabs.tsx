import { useId, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { cn } from '../../lib/utils'
import { DUR, EASE_OUT_EXPO } from '../../lib/motion'

export interface TabItem<K extends string = string> {
  key: K
  label: ReactNode
  /** 右侧的条数。0 也照常显示——「这一类没有」和「没取到数」是两件事。 */
  count?: number
}

/** 页签。
 *
 *  全站只有这一套：灰底胶囊 + 跟随选中的白色指示块。原来的「下划线页签」（模型列表）
 *  和「胶囊页签」（记忆列表）是两套写法，同一层级的导航长得不一样。
 *
 *  指示块用 `layoutId` 让它跟着选中项滑动；系统开了「减少动态效果」时自动退化为
 *  直接切换（`useReducedMotion`），不做位移动画。 */
export function Tabs<K extends string>({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem<K>[]
  value: K
  onChange: (key: K) => void
  /** 无障碍名称，如「记忆类型」 */
  label?: string
  className?: string
}) {
  const id = useId()
  const reduce = useReducedMotion()

  return (
    <div
      role="tablist"
      aria-label={label}
      className={cn('inline-flex w-fit items-center gap-1 rounded-xl border border-line bg-surface-muted p-1', className)}
    >
      {items.map((item) => {
        const active = item.key === value
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={cn(
              'relative inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-3 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
              active ? 'text-ink' : 'text-ink-muted hover:bg-surface-hover/70 hover:text-ink',
            )}
          >
            {active && (
              <motion.span
                layoutId={`tab-${id}`}
                className="absolute inset-0 rounded-lg border border-line bg-surface shadow-2xs"
                transition={reduce ? { duration: 0 } : { type: 'tween', duration: DUR.base, ease: EASE_OUT_EXPO }}
              />
            )}
            <span className="relative">{item.label}</span>
            {item.count !== undefined && (
              <span className={cn('relative text-[11px] tabular-nums', active ? 'text-ink-secondary' : 'text-ink-faint')}>
                {item.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
