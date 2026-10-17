/** 接口封装，权威定义见仓库根目录 openapi.json。换真后端时前端不动。 */

import { API_BASE } from './config'

/* ------------------------------------------------------------ 请求层 */

export class ApiError extends Error {
  status: number
  code?: number
  constructor(message: string, status: number, code?: number) {
    super(message)
    this.status = status
    this.code = code
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
  const res = await fetch(`${API_BASE}${path}${query ? qs(query) : ''}`, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const text = await res.text()
  let parsed: unknown
  try {
    parsed = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(`响应不是 JSON（HTTP ${res.status}）`, res.status)
  }

  const env = parsed as { code?: number; data?: unknown; message?: string } | null
  if (!res.ok) throw new ApiError(env?.message || `请求失败（HTTP ${res.status}）`, res.status, env?.code)
  if (env && typeof env.code === 'number' && env.code !== 0) {
    throw new ApiError(env.message || `接口返回 code=${env.code}`, res.status, env.code)
  }
  return (env && 'data' in env ? env.data : parsed) as T
}

/* -------------------------------------------------------------- 类型 */

/** 几乎所有接口都要它的 id */
export interface Project {
  id: string
  name: string
  description?: string
  /** "ENABLED" 的那条是当前项目 */
  status?: string
  createTime?: string
  isMultiView?: number
}

export interface ApiKey {
  id: string
  keyName: string
  /** 完整密钥，列表里也下发；展示时前端自己截断 */
  apiKey: string
  createTime: string
}

/** 调用日志行 */
export interface RequestLog {
  id: string
  createTime: string
  /** 事件类型，见 EVENT_TYPES；extractMemoryDirect 展示成 extractMemory */
  eventType: string
  userIds?: string[]
  agentIds?: string[]
  status: string
  duration?: number
}

/** 调用日志详情。requestBody / responseBody 是 JSON 字符串，前端要二次 parse */
export interface LogDetail extends Omit<RequestLog, 'userIds' | 'agentIds'> {
  traceId?: string
  userId?: string
  agentId?: string
  requestTokens?: number
  responseTokens?: number
  requestCode?: number
  responseCode?: number
  requestBody?: string
  responseBody?: string
}

export interface Memory {
  memoryId: string
  memoryContent: string
  /** user | agent | public */
  subjectType: string
  externalUserId: string
  createTime: string
  /** skill_mem 专有 */
  skillName?: string
  skillUrl?: string
  /** profile_mem 专有 */
  profileTemplateId?: string
  profileInstanceId?: string
}

export interface KnowledgeBase {
  kbId: string
  knowledgebaseName: string
  knowledgebaseDescription?: string
  projectIds?: string[]
}

/** 属性树模板。字段结构是「分组 → 字段 → { value, algorithm_updatable }」 */
export interface ProfileTemplate {
  templateId: string
  templateName: string
  bindingCount?: number
  updatedAt?: string
  [k: string]: unknown
}

export interface UsageDailyStat {
  date: string
  addMessage?: { calls?: number; totalTokens?: number }
  searchMemory?: { calls?: number; totalTokens?: number }
  chat?: { requestTokens?: number; responseTokens?: number; totalTokens?: number }
  extractMemory?: { requestTokens?: number; responseTokens?: number; totalTokens?: number }
  rerank?: { requestTokens?: number; totalTokens?: number }
}

/* ------------------------------------------------ 各接口的返回形状 */

export interface Records<T> {
  records: T[]
  total: number
  current?: number
  size?: number
}

/* ------------------------------------------------------------ 接口 */

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

/** 记忆列表标签；Memories.tsx 另加了 profile_mem */
export const MEMORY_DETAIL_TYPES = [
  { type: 'text_mem', label: '事实记忆' },
  { type: 'pref_mem', label: '偏好记忆' },
  { type: 'event_mem', label: '事件记忆' },
  { type: 'skill_mem', label: '技能' },
  { type: 'tool_mem', label: '工具记忆' },
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

  /** 属性树模板。注意这个接口的列表键是 list，不是 records */
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

  meta: () => call<Meta>('/api/meta', { method: 'GET' }),
}

/* ------------------------------------------------- 扩展接口的类型 */

export type DataSource = 'live' | 'sample'

/** 接入说明与示例命令据此生成 */
export interface ToolInfo {
  name: string
  title: string
}

export interface Meta {
  mode: DataSource
  service: string
  health: Record<string, unknown> | null
  /** 密钥前缀，新建密钥的展示与校验用它 */
  keyPrefix: string
  tools: ToolInfo[]
}
