import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Icon } from './Icon'
import { pageTitleKey } from '../lib/nav'
import { TOPBAR_LINK } from '../lib/cls'
import { LINKS } from '../lib/config'
import { useLang, useMeta, useStr, useT } from '../lib/store'
import type { TKey } from '../lib/i18n'

const ITEM = 'flex items-center text-[#62748E] last:text-[#0F172B] space-x-2 text-sm leading-5.5'

export function TopBar() {
  const { pathname } = useLocation()
  const t = useT()
  const str = useStr()
  const { lang, setLang } = useLang()
  const [menuOpen, setMenuOpen] = useState(false)
  const { meta } = useMeta()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const titleKey = pageTitleKey(pathname) as TKey | undefined

  return (
    <div className="flex items-center justify-between h-14 px-5 py-4.5">
      <ul className="flex gap-3">
        <li className={ITEM}>
          <Icon name="i-db-dashboard" />
          <span>{t('app.console')}</span>
        </li>
        <li className={ITEM}>
          <span>/</span>
          <span>{titleKey ? str(titleKey) : ''}</span>
        </li>
      </ul>

      <div className="flex gap-3">
        {meta && (
          <span
            title={meta.mode === 'live' ? t('meta.liveTip')(meta.service) : t('meta.sampleTip')}
            className={`inline-flex items-center gap-1 rounded-[6px] border px-2 py-0.5 text-xs ${
              meta.mode === 'live' ? 'border-[#a7f3d0] bg-[#ecfdf5] text-[#047857]' : 'border-[#fed7aa] bg-[#fff7ed] text-[#c2410c]'
            }`}
          >
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: meta.mode === 'live' ? '#047857' : '#c2410c' }}
            />
            {meta.mode === 'live' ? t('meta.live') : t('meta.sample')}
          </span>
        )}
        <a href={LINKS.home} rel="noopener noreferrer" target="_blank" className={TOPBAR_LINK}>
          <Icon name="i-db-logo" className="size-6 size-6.5!" />
          <span>{t('topbar.home')}</span>
        </a>
        <Link to={LINKS.about} className={TOPBAR_LINK}>
          <Icon name="i-ll-about" className="size-6 undefined" />
          <span>{t('topbar.about')}</span>
        </Link>
        <Link to={LINKS.docs} className={TOPBAR_LINK}>
          <Icon name="i-ll-helpdoc" className="size-6 size-5!" />
          <span>{t('topbar.docs')}</span>
        </Link>

        <div className="relative" ref={ref}>
          <button type="button" aria-label={t('topbar.lang')} className={TOPBAR_LINK} onClick={() => setMenuOpen((o) => !o)}>
            <Icon name="i-ll-i18n" className="size-6 size-5.5!" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 z-50 w-32 rounded-[8px] border border-[#E2E8F0] bg-white shadow-lg py-1">
              {(
                [
                  ['zh', '简体中文'],
                  ['en', 'English'],
                ] as const
              ).map(([code, label]) => (
                <button
                  key={code}
                  type="button"
                  className={`w-full text-left px-3 py-2 text-sm hover:bg-[#f7f8fb] ${lang === code ? 'text-primary' : 'text-[#314158]'}`}
                  onClick={() => {
                    setLang(code)
                    setMenuOpen(false)
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
