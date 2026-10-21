import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ApiError } from './api'
import { errText } from './i18n'
import { useLang } from './store'

export type AsyncState = 'loading' | 'ready' | 'error'

/** 统一处理「加载中 / 成功 / 失败」，并在依赖变化时重新取数。
 *
 *  已深度接入 TanStack Query v5：
 *    - 自动具备跨页面缓存、并发请求去重与后台静默刷新
 *    - 保留原先对外的简洁接口 { data, state, error, reload }，现有页面零负担升级
 *
 *  `skip` 为真时 query disabled，状态保持 loading 直到 ready。 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[], { skip = false }: { skip?: boolean } = {}) {
  const { lang } = useLang()

  const {
    data = null,
    status,
    error,
    refetch,
  } = useQuery<T, unknown>({
    queryKey: ['useAsync', ...deps],
    queryFn: fn,
    enabled: !skip,
    // status 0 是 fetch 层失败（`api.ts` 里标出来的），说明 BFF 正在重启：
    // 重试 6 次、退避到 8 秒，总共约 30 秒，覆盖 Recreate 部署的空窗期。
    // HTTP 4xx/5xx 不重试——重试不会让它变好，只会把错误提示推迟半分钟。
    retry: (count, error) => (error instanceof ApiError && error.status === 0 ? count < 6 : count < 1),
    retryDelay: (n) => Math.min(1000 * 2 ** n, 8000),
  })

  const state: AsyncState = skip || status === 'pending' ? 'loading' : status === 'error' ? 'error' : 'ready'

  return {
    data: data ?? null,
    state,
    error: error ? errText(lang, error) : '',
    reload: () => {
      refetch()
    },
  }
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
