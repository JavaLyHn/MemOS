import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Logo } from './Logo'
import { Icon } from './Icon'
import { NAV_GROUPS } from '../lib/nav'
import { BTN_FOLD, BTN_PROJECT, NAV_ITEM, NAV_LINK } from '../lib/cls'
import { useProject, useStr, useT } from '../lib/store'
import { LINKS } from '../lib/config'
import type { TKey } from '../lib/i18n'

/** 侧栏组件的作用域属性，组件级 CSS 依赖它命中 */
const S = { 'data-v-bc08aa60': '' } as const
const P = { 'data-v-ede8bedc': '' } as const
const U = { 'data-v-4079c7a3': '' } as const

const COLLAPSE_KEY = 'console.sidebar.collapsed'
const W_EXPANDED = 200
const W_COLLAPSED = 68
const RAIL_ITEM = 44

export function Sidebar() {
  const { pathname } = useLocation()
  const t = useT()
  const str = useStr()
  const { currentProjectId, currentProjectName, projects, setCurrent } = useProject()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === '1')
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const toggleCollapse = () => {
    setCollapsed((c) => {
      localStorage.setItem(COLLAPSE_KEY, c ? '0' : '1')
      return !c
    })
    setPickerOpen(false)
  }

  const currentName = currentProjectName || t('nav.selectProject')

  return (
    <div
      {...S}
      style={{ width: collapsed ? W_COLLAPSED : W_EXPANDED }}
      className={`flex flex-col h-screen min-h-0 shrink-0 bg-[#f0f2f5] transition-all duration-300 overflow-hidden ${
        collapsed ? 'px-0 items-center' : 'px-4'
      }`}
    >
      <div {...S} className={`h-14 shrink-0 flex items-center ${collapsed ? 'justify-center' : ''}`}>
        <a {...S} href={LINKS.home} rel="noopener noreferrer" target="_blank">
          <Logo compact={collapsed} />
        </a>
      </div>

      <div {...S} className={`w-full shrink-0 mt-5 relative ${collapsed ? 'flex justify-center' : ''}`} ref={pickerRef}>
        {collapsed ? (
          <button
            type="button"
            title={currentName}
            onClick={() => setPickerOpen((o) => !o)}
            style={{ width: RAIL_ITEM, height: 38 }}
            className="rounded-[8px] border border-[#CBD5E1] bg-transparent flex items-center justify-center cursor-pointer hover:bg-white"
          >
            <span className="iconify i-db:arrow-right-left text-third-gray size-5" aria-hidden="true" />
          </button>
        ) : (
          <button type="button" className={BTN_PROJECT} onClick={() => setPickerOpen((o) => !o)}>
            <span {...P} className="truncate text-left">
              {currentName}
            </span>
            <span {...P} className="absolute top-0 right-2.5 bottom-0 flex items-center flex">
              <span {...P} className="iconify i-db:arrow-right-left text-third-gray size-5" aria-hidden="true" />
            </span>
          </button>
        )}

        {pickerOpen && (
          <div
            className="absolute z-50 mt-1 rounded-[8px] border border-[#E2E8F0] bg-white shadow-lg py-1"
            style={collapsed ? { left: 0, top: '100%', width: 200 } : { left: 0, right: 0, top: '100%' }}
          >
            {projects.length === 0 && <div className="px-3 py-2 text-sm text-[#94a3b8]">{t('nav.noProject')}</div>}
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`w-full text-left px-3 py-2 text-sm hover:bg-[#f7f8fb] flex items-center justify-between ${
                  currentProjectId === p.id ? 'text-primary' : 'text-[#314158]'
                }`}
                onClick={() => {
                  setCurrent(p.id).catch(() => {})
                  setPickerOpen(false)
                }}
              >
                <span className="truncate">{p.name}</span>
                {currentProjectId === p.id && <Icon name="i-lucide:check" className="ml-2 size-4 shrink-0" />}
              </button>
            ))}
          </div>
        )}
      </div>

      <div
        {...S}
        className={`dashboard-aside-scroll w-full flex-1 min-h-0 mt-3 space-y-3 overflow-y-auto overflow-x-hidden ${
          collapsed ? 'flex flex-col items-center' : ''
        }`}
      >
        <div {...S} className={`space-y-3 ${collapsed ? 'flex flex-col items-center' : 'w-full'}`}>
          {NAV_GROUPS.map((group) => (
            <div key={group.title} className={`space-y-1 ${collapsed ? 'flex flex-col items-center' : 'w-full'}`}>
              {!collapsed && <div className="px-2 pb-1 text-xs leading-5 text-third-gray/70">{str(group.title as TKey)}</div>}
              <ul className={`space-y-1.5 ${collapsed ? 'flex flex-col items-center' : ''}`}>
                {group.items.map((item) => {
                  const active = pathname === item.to
                  return (
                    <li
                      key={item.to}
                      title={str(item.label as TKey)}
                      style={collapsed ? { width: RAIL_ITEM } : undefined}
                      className={`${NAV_ITEM} ${active ? 'bg-white text-primary' : 'text-third-gray hover:bg-white hover:text-primary'}`}
                    >
                      <Link to={item.to} className={`${NAV_LINK} ${collapsed ? 'justify-center px-0' : ''}`}>
                        {item.img ? (
                          <div className="w-4 h-4 flex items-center justify-center shrink-0">
                            <img src={item.img} className="w-full h-full object-contain" alt="" />
                          </div>
                        ) : (
                          <Icon name={active && item.iconActive ? item.iconActive : item.icon!} className="w-4 h-4" />
                        )}
                        {!collapsed && <span className="text-[14px] leading-6">{str(item.label as TKey)}</span>}
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div {...S} className={`shrink-0 ${collapsed ? 'flex flex-col items-center w-full' : ''}`}>
        <button
          type="button"
          title={t('nav.collapse')}
          className={`${BTN_FOLD} ${collapsed ? 'justify-center px-0' : ''}`}
          style={collapsed ? { width: RAIL_ITEM } : undefined}
          onClick={toggleCollapse}
        >
          <Icon name="i-ll-fold" className="size-4 text-ink" />
          {!collapsed && <span className="w-[30px] text-sm font-normal color-[#62748E] ml-0.5 whitespace-nowrap">{t('nav.collapse')}</span>}
        </button>

        <ul {...S} className="space-y-1.5">
          <li
            title={t('nav.docs')}
            style={collapsed ? { width: RAIL_ITEM } : undefined}
            className={`${NAV_ITEM} text-third-gray hover:bg-white hover:text-primary`}
          >
            <Link to={LINKS.docs} className={`${NAV_LINK} ${collapsed ? 'justify-center px-0' : ''}`}>
              <Icon name="i-db-book" className="w-4 h-4" />
              {!collapsed && <span className="text-[14px] leading-6">{t('nav.docs')}</span>}
            </Link>
          </li>
        </ul>

        <Link
          {...S}
          to="/cn/usage"
          title={t('nav.freePlan')}
          style={{
            width: collapsed ? RAIL_ITEM : undefined,
            background: 'rgba(98, 116, 142, 0.06)',
            borderImage: 'linear-gradient(90deg, rgba(171, 187, 205, 0.3) 0%, rgba(98, 116, 142, 0.3) 99%) 1 / 1 / 0 stretch',
            color: 'rgb(98, 116, 142)',
          }}
          className={`rounded-[8px] font-medium group flex items-center whitespace-nowrap py-2.5 text-[14px] gap-x-1 h-11 mb-2 ${
            collapsed ? 'justify-center px-0' : 'px-2'
          }`}
        >
          <div className="flex items-center justify-center shrink-0">
            <Icon
              name="i-ri:money-cny-circle-line"
              style={{
                fontSize: '16px',
                background: 'linear-gradient(311deg, rgb(98, 116, 142) 13%, rgb(222, 228, 235) 106%)',
              }}
            />
          </div>
          {!collapsed && <span className="whitespace-nowrap overflow-hidden">{t('nav.freePlan')}</span>}
        </Link>

        <Link
          {...U}
          to={LINKS.about}
          title={t('nav.account')}
          style={{ width: collapsed ? RAIL_ITEM : undefined }}
          className={`border-t-[1px] border-[#E2E8F0] flex items-center cursor-pointer gap-[8px] ${
            collapsed ? 'justify-center py-3' : 'pt-4 pb-6 px-2 justify-between'
          }`}
        >
          <div
            {...U}
            className="rounded-full w-[36px] h-[36px] my-[3px] flex items-center justify-center text-letter shrink-0 text-white"
            style={{ backgroundColor: 'rgb(134, 137, 244)' }}
          >
            G
          </div>
          {!collapsed && (
            <div {...U} className="truncate text-[14px] font-400 leading-[20px] text-[#606266]">
              {t('nav.account')}
            </div>
          )}
          {!collapsed && <img {...U} src="/icons/user-arrow.svg" className="w-[16px] h-[16px]" alt="" />}
        </Link>
      </div>
    </div>
  )
}
