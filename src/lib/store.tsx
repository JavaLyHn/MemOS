import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { DICTS, type Lang, type TKey } from './i18n'
import { api, type Meta, type Project, type ToolInfo } from './api'

const LANG_KEY = 'console.lang'

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  /** t('nav.apikeys') 取词；少数词条是函数，直接调用 */
  t: <K extends TKey>(k: K) => (typeof DICTS)['zh'][K]
  /** 动态 key（非字面量）时用它，返回值一定是字符串 */
  str: (k: TKey) => string
}

const LangContext = createContext<LangCtx | null>(null)

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const saved = localStorage.getItem(LANG_KEY)
    return saved === 'en' ? 'en' : 'zh'
  })

  useEffect(() => {
    localStorage.setItem(LANG_KEY, lang)
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
  }, [lang])

  const value = useMemo<LangCtx>(
    () => ({
      lang,
      setLang: setLangState,
      t: (k) => DICTS[lang][k] as (typeof DICTS)['zh'][typeof k],
      str: (k) => String(DICTS[lang][k]),
    }),
    [lang],
  )

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>
}

export function useLang() {
  const c = useContext(LangContext)
  if (!c) throw new Error('useLang 必须在 LangProvider 内使用')
  return c
}

export function useT() {
  return useLang().t
}

export function useStr() {
  return useLang().str
}

interface Toast {
  id: number
  text: string
  kind: 'ok' | 'err'
}

const ToastContext = createContext<{ push: (text: string, kind?: 'ok' | 'err') => void } | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([])

  const push = useCallback((text: string, kind: 'ok' | 'err' = 'ok') => {
    const id = Date.now() + Math.random()
    setList((l) => [...l, { id, text, kind }])
    setTimeout(() => setList((l) => l.filter((t) => t.id !== id)), 2600)
  }, [])

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[999] flex flex-col gap-2 pointer-events-none">
        {list.map((t) => (
          <div
            key={t.id}
            className={`px-4 py-2 rounded-[8px] shadow-lg text-sm text-white ${t.kind === 'ok' ? 'bg-[#18181b]' : 'bg-[#dc2626]'}`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const c = useContext(ToastContext)
  if (!c) throw new Error('useToast 必须在 ToastProvider 内使用')
  return c.push
}

const PROJ_KEY = 'console.project'

interface ProjectCtx {
  /** 当前项目 id，所有业务接口的 projectId */
  currentProjectId: string
  currentProjectName: string
  projects: Project[]
  loading: boolean
  reload: () => void
  /** 切换当前项目：把它置为 ENABLED，后端会把其它项目置回 DISABLED */
  setCurrent: (id: string) => Promise<void>
}

const ProjectContext = createContext<ProjectCtx | null>(null)

/** 当前项目：dict 里 status === "ENABLED" 的那条，选择结果本地记住 */
export function ProjectProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const [picked, setPicked] = useState<string>(() => localStorage.getItem(PROJ_KEY) ?? '')

  useEffect(() => {
    let alive = true
    // 语言变了名字要重新取，这里的同步 setState 是刻意的
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    api.project
      .dict(lang === 'zh' ? 'zh-CN' : 'en-US')
      .then((list) => {
        if (!alive) return
        setProjects(list)
        setLoading(false)
      })
      .catch(() => {
        if (!alive) return
        setProjects([])
        setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [lang, tick])

  const enabled = projects.find((p) => p.status === 'ENABLED')
  // 后端的 ENABLED 优先；它没给就退到本地记住的那个
  const currentProjectId = enabled?.id || (projects.some((p) => p.id === picked) ? picked : '')

  const value = useMemo<ProjectCtx>(
    () => ({
      currentProjectId,
      currentProjectName: projects.find((p) => p.id === currentProjectId)?.name ?? '',
      projects,
      loading,
      reload: () => setTick((t) => t + 1),
      setCurrent: async (id: string) => {
        localStorage.setItem(PROJ_KEY, id)
        setPicked(id)
        await api.project.update({ id, status: 'ENABLED' })
        setTick((t) => t + 1)
      },
    }),
    [currentProjectId, projects, loading],
  )

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject() {
  const c = useContext(ProjectContext)
  if (!c) throw new Error('useProject 必须在 ProjectProvider 内使用')
  return c
}

interface MetaCtx {
  meta: Meta | null
  keyPrefix: string
  tools: ToolInfo[]
}

const FALLBACK_KEY_PREFIX = 'sk-'

const MetaContext = createContext<MetaCtx | null>(null)

/** 运行信息全局取一次，前端不写死 */
export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null)

  useEffect(() => {
    let alive = true
    api
      .meta()
      .then((m) => {
        if (alive) setMeta(m)
      })
      .catch(() => {
        if (alive) setMeta(null)
      })
    return () => {
      alive = false
    }
  }, [])

  const value = useMemo<MetaCtx>(
    () => ({
      meta,
      keyPrefix: meta?.keyPrefix || FALLBACK_KEY_PREFIX,
      tools: meta?.tools ?? [],
    }),
    [meta],
  )

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const c = useContext(MetaContext)
  if (!c) throw new Error('useMeta 必须在 MetaProvider 内使用')
  return c
}
