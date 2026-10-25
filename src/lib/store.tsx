import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { makeT, textOf, type Lang, type ParamEntries, type TKey } from './i18n'
import { api, type Account, type Meta, type Project, type ToolInfo } from './api'
import { DUR, EASE_IN_FAST, EASE_OUT_EXPO } from './motion'
import { Icon } from '../components/Icon'

const LANG_KEY = 'console.lang'

/** 取词：普通词条返回 string，带参数的词条返回函数（要再调一次，见 i18n.ts） */
export type TFn = <K extends TKey>(k: K) => K extends keyof ParamEntries ? ParamEntries[K] : string

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: TFn
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
      t: makeT(lang) as TFn,
      str: (k) => textOf(lang, k),
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

/** 提示条停留时长。
 *
 *  错误要留得久一些：上游 500 的原文往往两行都放不下，2.8 秒读到一半就没了，
 *  用户还得再触发一次同样的失败才看得到。成功提示看一眼就够，不必占着视线。 */
const TOAST_MS = { ok: 2600, err: 6000 } as const

export function ToastProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Toast[]>([])
  const reduce = useReducedMotion()
  const tr = useT()

  const dismiss = useCallback((id: number) => setList((l) => l.filter((x) => x.id !== id)), [])

  const push = useCallback(
    (text: string, kind: 'ok' | 'err' = 'ok') => {
      const id = Date.now() + Math.random()
      setList((l) => [...l, { id, text, kind }])
      setTimeout(() => dismiss(id), TOAST_MS[kind])
    },
    [dismiss],
  )

  return (
    <ToastContext.Provider value={{ push }}>
      {children}
      <div className="fixed top-5 left-1/2 -translate-x-1/2 z-[999] flex flex-col items-center gap-2 pointer-events-none">
        <AnimatePresence mode="popLayout">
          {list.map((t) => (
            <motion.div
              key={t.id}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: -12, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={
                reduce
                  ? { opacity: 0, transition: { duration: 0 } }
                  : { opacity: 0, y: -8, scale: 0.98, transition: { duration: DUR.fast, ease: EASE_IN_FAST } }
              }
              transition={reduce ? { duration: 0 } : { duration: DUR.base, ease: EASE_OUT_EXPO }}
              className={`toast toast--${t.kind} toast--dismissable`}
              role={t.kind === 'err' ? 'alert' : 'status'}
              aria-live={t.kind === 'err' ? 'assertive' : 'polite'}
              title={tr('common.close')}
              onClick={() => dismiss(t.id)}
            >
              <Icon name={t.kind === 'ok' ? 'i-lucide:check-circle-2' : 'i-lucide:alert-circle'} className="toast__icon" />
              <span className="toast__text">{t.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
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
  /** 项目字典是否已经落定（成功或失败都算）。
   *
   *  业务页取数要拿它做 `useAsync` 的 `skip`：首帧的 `currentProjectId` 还是空串，
   *  这时发出去的请求会被 BFF 直接拒（`40000 缺少 projectId`），页面先闪一段报错，
   *  等字典回来再打第二遍——一次加载同一份数据取两次。 */
  ready: boolean
  reload: () => void
  /** 切换当前项目：把它置为 ENABLED，后端会把其它项目置回 DISABLED */
  setCurrent: (id: string) => Promise<void>
}

const ProjectContext = createContext<ProjectCtx | null>(null)

/** 当前项目：dict 里 status === "ENABLED" 的那条，选择结果本地记住 */
export function ProjectProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang()
  const { reloadAccount } = useMeta()
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
      ready: !loading,
      reload: () => setTick((t) => t + 1),
      setCurrent: async (id: string) => {
        localStorage.setItem(PROJ_KEY, id)
        setPicked(id)
        await api.project.update({ id, status: 'ENABLED' })
        setTick((t) => t + 1)
        // 业务页和「当前项目」徽标都以 /api/auth/me 为准：不刷新的话切换只更新了
        // 侧边栏的勾选，页面内容仍按旧项目渲染。
        await reloadAccount()
      },
    }),
    [currentProjectId, projects, loading, reloadAccount],
  )

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProject() {
  const c = useContext(ProjectContext)
  if (!c) throw new Error('useProject 必须在 ProjectProvider 内使用')
  return c
}

interface MetaCtx {
  authEnabled: boolean
  canLogout: boolean
  meta: Meta | null
  account: Account | null
  /** 重取 `/api/auth/me`。切换当前项目后必须调：`currentProjectId` 只在登录时取一次，
   *  不刷新的话页面上的「当前项目」标记会停在切换前那一条。 */
  reloadAccount: () => Promise<void>
  /** 真实身份是否是平台管理员（预览模式不影响它，供菜单显示开关）。 */
  realAdmin: boolean
  /** 预览普通用户视角：只把 `platformAdmin` 从 UI 上隐藏，不改任何权限。 */
  previewUser: boolean
  setPreviewUser: (v: boolean) => void
  keyPrefix: string
  tools: ToolInfo[]
}

const FALLBACK_KEY_PREFIX = 'sk-'

const MetaContext = createContext<MetaCtx | null>(null)

/** 运行信息全局取一次，前端不写死 */
const PREVIEW_KEY = 'console.previewUser'

export function MetaProvider({ children }: { children: ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null)
  const [account, setAccount] = useState<Account | null>(null)
  const [previewUser, setPreviewUserState] = useState(() => localStorage.getItem(PREVIEW_KEY) === '1')
  const setPreviewUser = useCallback((v: boolean) => {
    localStorage.setItem(PREVIEW_KEY, v ? '1' : '0')
    setPreviewUserState(v)
  }, [])

  const reloadAccount = useCallback(async () => {
    try {
      setAccount(await api.auth.me())
    } catch {
      setAccount(null)
    }
  }, [])

  useEffect(() => {
    let alive = true
    api
      .meta()
      .then((m) => {
        if (!alive) return
        setMeta(m)
        if (m.authEnabled) void reloadAccount()
      })
      .catch(() => {
        if (alive) {
          setMeta(null)
          setAccount(null)
        }
      })
    return () => {
      alive = false
    }
  }, [reloadAccount])

  const realAdmin = account?.platformAdmin === true
  // 预览模式把 platformAdmin 从界面上拿掉，页面里的管理员入口（用户页签、指派项目、
  // 管理员徽标）会按普通用户渲染；后端权限完全不受影响，这是给自己看视角用的。
  const visibleAccount = useMemo(
    () => (previewUser && realAdmin && account ? { ...account, platformAdmin: false } : account),
    [previewUser, realAdmin, account],
  )

  const value = useMemo<MetaCtx>(
    () => ({
      meta,
      account: visibleAccount,
      reloadAccount,
      realAdmin,
      previewUser,
      setPreviewUser,
      keyPrefix: meta?.keyPrefix || FALLBACK_KEY_PREFIX,
      tools: meta?.tools ?? [],
      authEnabled: Boolean(meta?.authEnabled),
      canLogout: Boolean(meta?.authEnabled) && meta?.authMode !== 'basic',
    }),
    [meta, visibleAccount, realAdmin, previewUser, setPreviewUser, reloadAccount],
  )

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const c = useContext(MetaContext)
  if (!c) throw new Error('useMeta 必须在 MetaProvider 内使用')
  return c
}
