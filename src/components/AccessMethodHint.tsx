/** 「选择哪种接入方式？」悬浮说明。结构与类名逐字取自设计稿。 */

import { useRef, useState } from 'react'
import { useT } from '../lib/store'

/** 样式都挂在作用域属性下，类名不带它就不生效 */
const Q = { 'data-v-de9e37d2': '' } as const

/** 表格的三种单元格，同一套边框 + 内边距，只有首列和表头加粗、不换行 */
const CELL = 'border border-[#ebeef5] px-2.5 py-1.5 align-top'
const CELL_HEAD = 'border border-[#ebeef5] bg-[#f8fafc] px-2.5 py-1.5 font-medium text-[#18181b] whitespace-nowrap'
const CELL_NAME = `${CELL} font-medium text-[#18181b] whitespace-nowrap`

/** 鼠标要能从提示文字滑进浮层，所以进出都走外层容器；关闭留一点延迟免得闪 */
const CLOSE_DELAY = 120

export function AccessMethodHint({ text }: { text: string }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const show = () => {
    window.clearTimeout(timer.current)
    setOpen(true)
  }
  const hide = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOpen(false), CLOSE_DELAY)
  }

  const rows: Array<[string, string, string]> = [
    ['Plugin', t('quickstart.hint.plugin.scene'), t('quickstart.hint.plugin.feature')],
    ['CLI + Skill', t('quickstart.hint.cli.scene'), t('quickstart.hint.cli.feature')],
    ['MCP', t('quickstart.hint.mcp.scene'), t('quickstart.hint.mcp.feature')],
  ]

  return (
    <span className="relative inline-flex" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      <span
        {...Q}
        tabIndex={0}
        className="access-method-hint cursor-help outline-none"
        aria-expanded={open}
        data-state={open ? 'open' : 'closed'}
      >
        {text}
      </span>

      {open && (
        <div
          role="tooltip"
          data-state="open"
          data-side="bottom"
          data-align="end"
          className="absolute right-0 top-full mt-3 z-50 data-[state=open]:animate-[scale-in_100ms_ease-out] focus:outline-none pointer-events-auto access-method-pop max-w-[560px] p-3 bg-white text-[#334155] rounded-xl ring-1 ring-[#ebeef5] shadow-lg"
          /* 宽度来自 popper 的 min-width: max-content（实测 560px），
             缩放原点来自 popper 变量；这里不走 popper，两项都直接给：
             宽度同宽、窄屏留 1rem 边距，原点钉在右上角（箭头那一侧） */
          style={{ width: 'min(560px, calc(100vw - 1rem))', transformOrigin: 'top right' }}
        >
          <div className="text-[12px] leading-[1.6]">
            <table className="access-method-table w-full border-collapse text-left">
              <thead>
                <tr>
                  <th className={CELL_HEAD}>{t('quickstart.hint.col.method')}</th>
                  <th className={CELL_HEAD}>{t('quickstart.hint.col.scene')}</th>
                  <th className={CELL_HEAD}>{t('quickstart.hint.col.feature')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([name, scene, feature]) => (
                  <tr key={name}>
                    <td className={CELL_NAME}>{name}</td>
                    <td className={CELL}>{scene}</td>
                    <td className={CELL}>{feature}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 mb-0 text-[#71717a]">{t('quickstart.hint.footer')}</p>
          </div>
          {/* 箭头贴在浮层上方，横向对准提示文字的中心。这几个偏移量在编译 CSS 里
              没有对应工具类（它是 popper 运行时算出来的），所以直接写内联样式 */}
          <span className="absolute" style={{ top: 0, right: 54, transform: 'translateY(-100%)' }}>
            <svg width="10" height="5" viewBox="0 0 12 6" preserveAspectRatio="none" className="fill-white block">
              <path d="M0 0L6 6L12 0" />
            </svg>
          </span>
        </div>
      )}
    </span>
  )
}
