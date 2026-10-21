/** 接口封装，权威定义见仓库根目录 openapi.json。换真后端时前端不动。 */

import { API_BASE } from './config'
import type { TKey } from './i18n'
import type {
  ApiKey,
  DataSource,
  GraphLink,
  GraphLinkKind,
  GraphNode,
  KnowledgeBase,
  LogDetail,
  Memory,
  MemoryGraph,
  Meta,
  ModelRecord,
  ProfileTemplate,
  Project,
  Records,
  RequestLog,
  ToolInfo,
  UsageDailyStat,
} from '../../shared/contract'

/** 页面照旧从 `lib/api` 取这些类型；定义只有 `shared/contract.ts` 一份 */
export type {
  ApiKey,
  DataSource,
  GraphLink,
  GraphLinkKind,
  GraphNode,
  KnowledgeBase,
  LogDetail,
  Memory,
  MemoryGraph,
  Meta,
  ModelRecord,
  ProfileTemplate,
  Project,
  Records,
  RequestLog,
  ToolInfo,
  UsageDailyStat,
}

/* ------------------------------------------------------------ 请求层 */

export class ApiError extends Error {
  status: number
  code?: number
  /** **本地生成**的错误：文案键 + 插值参数，展示时按当前语言取词（见 `errText`）。
   *
   *  ⚠️ 上游返回的 message 不带它，那条路原样显示服务端原文，不翻译。
   *  所以这里的 `message` 只是一句给日志看的英文/技术描述，**不是给用户看的文案**。 */
  msg?: { key: TKey; args: unknown[] }

  constructor(message: string, status: number, code?: number, msg?: { key: TKey; args: unknown[] }) {
    super(message)
    this.status = status
    this.code = code
    this.msg = msg
  }
}

interface CallOpts {
  method?: 'GET' | 'POST'
  body?: unknown
  query?: Record<string, unknown>
}

const qs = (params: Record<string, unknown>) => {
  const u = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
  const s = u.toString()
  return s ? `?${s}` : ''
}

/** 发一次请求并解包。code === 0 返回 data，否则抛 ApiError。 */
async function call<T>(path: string, opts: CallOpts = {}): Promise<T> {
  const { method = 'POST', body, query } = opts
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}${query ? qs(query) : ''}`, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    // 唯一没有 HTTP 状态码的失败路径：BFF 正在重启（Recreate 部署会短暂没有 Pod）、
    // DNS 解析失败、连接被重置。用 status=0 标出来，`useAsync` 据此重试。
    // 其它错误都走下面的 HTTP 分支，带着真实状态码。
    throw new ApiError('network error', 0, undefined, { key: 'error.network', args: [] })
  }

  const text = await res.text()
  let parsed: unknown
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(`HTTP ${res.status}: response is not JSON`, res.status, undefined, {
      key: 'error.notJson',
      args: [res.status],
    })
  }

  const env = parsed as { code?: number; data?: unknown; message?: string } | null
  // 上游给了 message 就用它（服务端原文，不翻译）；没给才回落到本地文案
  if (!res.ok) {
    throw new ApiError(
      env?.message || `HTTP ${res.status}`,
      res.status,
      env?.code,
      env?.message ? undefined : { key: 'error.requestFailed', args: [res.status] },
    )
  }
  if (env && typeof env.code === 'number' && env.code !== 0) {
    throw new ApiError(
      env.message || `code=${env.code}`,
      res.status,
      env.code,
      env.message ? undefined : { key: 'error.code', args: [env.code] },
    )
  }
  return (env && 'data' in env ? env.data : parsed) as T
}

/* -------------------------------------------------------------- 类型 */

/* 传输形状在 `shared/contract.ts`，这里只留**页面查询参数**。 */

/** 调用日志的事件类型。列表页筛选下拉是前 10 个；后 4 个只出现在详情页的字段表里 */
export const EVENT_TYPES = [
  'addMessage',
  'searchMemory',
  'getMemory',
  'deleteMemory',
  'addFeedback',
  'manualAddMemory',
  'updateMemory',
  'bindProfileTemplate',
  'editProfile',
  'deleteProfile',
] as const

export interface MemoryListQuery {
  projectId: string
  memoryDetailType: string
  pageNum?: number
  pageSize?: number
  knowledgeBaseId?: string
  startTime?: string
  endTime?: string
  externalUserId?: string
  subjectType?: string
  memSearchContent?: string
}

export interface LogListQuery {
  projectId: string
  pageNum?: number
  pageSize?: number
  subjectId?: string
  subjectType?: string
  eventType?: string
  query?: string
  status?: string
  startTime?: string
  endTime?: string
}

export const api = {
  project: {
    dict: (language: string) => call<Project[]>('/api/dashboard/project/dict', { method: 'GET', query: { language } }),
    list: (pageNum = 1, pageSize = 10) => call<Records<Project>>('/api/dashboard/project/list', { body: { pageNum, pageSize } }),
    create: (body: { name: string; description: string; isMultiView: 0 | 1 }) => call<Project>('/api/dashboard/project/create', { body }),
    update: (body: Partial<Project> & { id: string }) => call<Project>('/api/dashboard/project/update', { body }),
    /** 切换当前项目就是把它置为 ENABLED */
    revoke: (id: string) => call<unknown>(`/api/dashboard/project/revoke/${encodeURIComponent(id)}`),
  },

  keys: {
    list: (projectId: string, pageNum = 1, pageSize = 10) =>
      call<Records<ApiKey>>('/api/dashboard/keys/list', { body: { projectId, pageNum, pageSize } }),
    create: (projectId: string, keyName: string) => call<ApiKey>('/api/dashboard/keys/create', { body: { projectId, keyName } }),
    revoke: (apiKeyId: string) => call<unknown>(`/api/dashboard/keys/revoke/${encodeURIComponent(apiKeyId)}`),
    /** 取完整密钥。列表里那份只是展示用 */
    copy: (apiKeyId: string) => call<string>('/api/dashboard/keys/copy', { body: { apiKeyId } }),
  },

  log: {
    list: (q: LogListQuery) => {
      // 空值不发出去
      const body: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== '') body[k] = v
      return call<{ logs: RequestLog[]; total: number }>('/api/dashboard/log/list', { body })
    },
    detail: (logId: string) => call<LogDetail>('/api/dashboard/log/detail', { body: { logId } }),
  },

  memory: {
    list: (q: MemoryListQuery) => {
      const body: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== '') body[k] = v
      return call<{ memListItemResponseList: Memory[]; total: number; current: number }>('/api/dashboard/project/memory/list', { body })
    },
    detail: (memoryId: string, memType: string) => call<Memory>('/api/dashboard/project/memory/detail', { body: { memoryId, memType } }),
    remove: (memory_ids: string[], memType: string) =>
      call<unknown>('/api/dashboard/project/memory/delete', { body: { memory_ids, memType } }),
  },

  knowledgeBase: {
    list: (pageNum = 1, pageSize = 10, name = '', projectId = '') =>
      call<Records<KnowledgeBase>>('/api/dashboard/knowledgebase/list', { body: { pageNum, pageSize, name, projectId } }),
    create: (body: { knowledgebaseName: string; knowledgebaseDescription: string; projectIds: string[] }) =>
      call<unknown>('/api/dashboard/knowledgebase/create', { body }),
    update: (id: string, body: { knowledgebaseName: string; knowledgebaseDescription: string; projectIds: string[] }) =>
      call<unknown>('/api/dashboard/knowledgebase/update', { body: { id, ...body } }),
    detail: (knowledgeBaseId: string) => call<KnowledgeBase>('/api/dashboard/knowledgebase/detail', { body: { knowledgeBaseId } }),
    projectAssociate: (projectId: string, knowledgeBaseIds: string[]) =>
      call<unknown>('/api/dashboard/knowledgebase/project/associate', { body: { projectId, knowledgeBaseIds } }),
    projectRemove: (body: { projectId: string; knowledgeBaseId: string; deleteAll?: boolean }) =>
      call<unknown>('/api/dashboard/knowledgebase/project/remove', { body }),
    fileList: (knowledgeBaseId: string, pageNum = 1, pageSize = 10) =>
      call<Records<Record<string, unknown>>>('/api/dashboard/knowledgebase/file/list', { body: { knowledgeBaseId, pageNum, pageSize } }),
    memoryList: (knowledgeBaseId: string, pageNum = 1, pageSize = 10) =>
      call<Records<Memory>>('/api/dashboard/knowledgebase/memory/list', { body: { knowledgeBaseId, pageNum, pageSize } }),
  },

  /** 画像模板。注意这个接口的列表键是 list，不是 records */
  profileTemplate: {
    list: (pageNum = 1, pageSize = 10, projectId = '') =>
      call<{ list: ProfileTemplate[]; total: number; current: number; size: number; pages: number }>(
        '/api/dashboard/profileTemplate/list',
        {
          body: { pageNum, pageSize, projectId },
        },
      ),
    detail: (templateId: string, projectId: string) =>
      call<ProfileTemplate>('/api/dashboard/profileTemplate/detail', { method: 'GET', query: { templateId, projectId } }),
    create: (body: Record<string, unknown>) => call<unknown>('/api/dashboard/profileTemplate/create', { body }),
    update: (body: Record<string, unknown>) => call<unknown>('/api/dashboard/profileTemplate/update', { body }),
    remove: (projectId: string, templateId: string) =>
      call<unknown>('/api/dashboard/profileTemplate/delete', { body: { projectId, templateId } }),
  },

  usage: {
    /** projectId 传 "all" 时前端改写成空串再发出，后端按全部处理 */
    query: (q: { projectId?: string; apiKeyId?: string; startDate: string; endDate: string }) =>
      call<{ dailyStats: UsageDailyStat[] }>('/api/dashboard/usage/query', { body: { ...q, includeDailyDetails: true } }),
  },

  promptConfig: {
    detail: (body: Record<string, unknown>) => call<Record<string, unknown>>('/api/dashboard/prompt-config/detail', { body }),
    save: (body: Record<string, unknown>) => call<unknown>('/api/dashboard/prompt-config/save', { body }),
    generate: (body: Record<string, unknown>) => call<Record<string, unknown>>('/api/dashboard/prompt-config/generate', { body }),
    resetDefault: (body: Record<string, unknown>) => call<Record<string, unknown>>('/api/dashboard/prompt-config/reset-default', { body }),
    debugExtract: (body: Record<string, unknown>) => call<Record<string, unknown>>('/api/dashboard/prompt-config/debug/extract', { body }),
  },

  skill: {
    skillMD: (oss_url: string) => call<string>('/api/dashboard/skill/skillMD', { body: { oss_url } }),
  },

  user: {
    quotaSummary: (knowledgebaseId?: string) =>
      call<Record<string, unknown>>('/api/user/quota/summary', { method: 'GET', query: { knowledgebaseId } }),
    subscriptionDetails: () =>
      call<{ cycles?: { id: string; cycleStartTime?: string; cycleEndTime?: string }[]; currentCycle?: { id: string } }>(
        '/api/user/subscription/details',
        { body: { cycleId: '', includeAllCycles: true } },
      ),
  },

  /* -------------------------------------------- 以下是本控制台的扩展 */

  /** 记忆星座图。**GET**：只读视图，参数放 query，浏览器能直接点开、能 curl 重放排障。
   *  它不是 openapi.json 里的接口，是展示层自己加的。 */
  graph: {
    memories: (q: { tenant?: string; types?: string; limit?: number }) =>
      call<MemoryGraph>('/api/dashboard/graph/memories', { method: 'GET', query: q }),
    /** 单条记忆的**全文**（抽屉里的「展开全文」）。与节点同源，都来自图库——
     *  洞察记忆在上游 REST 里查不到（`get_memory` 回 not found），所以不能走那条。 */
    memory: (id: string, tenant?: string) =>
      call<{ id: string; memory: string }>('/api/dashboard/graph/memory', { method: 'GET', query: { id, tenant } }),
  },

  /** 模型清单。读的是**上游 Pod 真正在读的那份 ConfigMap**，不是前端的静态副本——
   *  之前那页读 `public/tech-config/*.json`，模型名是编的（用户 2026-10-19 看出来了）。 */
  models: {
    list: () => call<{ records: ModelRecord[] }>('/api/dashboard/models', { method: 'GET' }),
  },

  meta: () => call<Meta>('/api/meta', { method: 'GET' }),
}
