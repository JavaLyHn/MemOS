import { useCallback, useEffect, useState } from 'react'

export type AsyncState = 'loading' | 'ready' | 'error'

/** 统一处理「加载中 / 成功 / 失败」，并在依赖变化时重新取数。 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [state, setState] = useState<AsyncState>('loading')
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let alive = true
    // 依赖变了就要退回「加载中」，这里的同步 setState 是刻意的
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState('loading')
    fn()
      .then((d) => {
        if (!alive) return
        setData(d)
        setState('ready')
        setError('')
      })
      .catch((e: unknown) => {
        if (!alive) return
        setError(e instanceof Error ? e.message : String(e))
        setState('error')
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  return { data, state, error, reload }
}

/** 列表页的翻页 + 搜索状态 */
export function usePaged(pageSize = 10) {
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [draft, setDraft] = useState('')
  return {
    page,
    pageSize,
    q,
    draft,
    setDraft,
    submit: () => {
      setQ(draft.trim())
      setPage(1)
    },
    reset: () => {
      setDraft('')
      setQ('')
      setPage(1)
    },
    setPage,
  }
}
