/** 前后端共用的接口契约。
 *
 *  这里是**唯一**的字段定义处：前端 `src/lib/api.ts` 直接再导出这些类型，后端
 *  按同一形状实现。以前两边各写一份（`RequestLog` vs
 *  `ConsoleLogRow`、`MemoryGraph` 两处、`ModelRecord` 两处），改一边忘另一边时
 *  TypeScript 不会报错，只有页面上少一列才看得出来。
 *
 *  ⚠️ 只放**跨进程传输的形状**。查询参数、页面内部状态、上游原始结构不要放进来。
 */

/* ------------------------------------------------------------ 信封 */

/** 前端统一从 `data` 里取；列表接口的 `data` 就是这个形状 */
export interface Records<T> {
  records: T[]
  total: number
  current?: number
  size?: number
}

/* ------------------------------------------------------------ 项目 */

export interface Project {
  id: string
  name: string
  description?: string
  /** "ENABLED" 的那条是当前项目 */
  status?: string
  createTime?: string
  isMultiView?: number
  /** 当前账号在这个项目里的角色；项目列表接口才带 */
  role?: string
  /** 项目已被管理员停用；和「不是当前项目」的 status=DISABLED 不是一件事 */
  disabled?: boolean
  /** personal 是账号的个人空间，team 是普通项目 */
  kind?: 'team' | 'personal'
  /** 已归档（软删除）；项目列表接口会带出，可恢复 */
  archived?: boolean
  archivedAt?: string
}

/* ------------------------------------------------------------ 账号与成员 */

export interface AdminAccount {
  id: string
  username: string
  display_name: string
  email?: string
  platform_admin: boolean
  disabled: boolean
  created_at: string
  last_login_at?: string
}

export interface ProjectMember {
  account_id: string
  username: string
  display_name: string
  disabled: boolean
  role: string
  created_at: string
}

/** `@` 搜索的可加入候选；member 表示已在项目里 */
export interface MemberCandidate {
  accountId: string
  username: string
  displayName: string
  disabled: boolean
  member: boolean
}

/** 项目邀请链接。明文 token 只在创建响应里出现一次（path），列表不含 token */
export interface ProjectInvite {
  id: string
  tenantId: string
  role: string
  status: 'active' | 'used' | 'expired' | 'revoked'
  createdAt: string
  expiresAt: string
  usedAt?: string
  usedByAccountId?: string
  revokedAt?: string
}

export interface CreatedInvite {
  id: string
  tenantId: string
  role: string
  path: string
  createdAt: string
  expiresAt: string
}

/* ------------------------------------------------------------ 密钥 */

export interface ApiKey {
  id: string
  keyName: string
  /** 完整密钥；展示时前端自己截断 */
  apiKey: string
  createTime: string
}

/* ------------------------------------------------------------ 调用日志 */

/** 调用日志列表行 */
export interface RequestLog {
  id: string
  /** 异步 add 的请求行与后台终态行的关联 ID；同步/历史行为空 */
  callId?: string
  createTime: string
  /** 事件类型，见前端 `EVENT_TYPES` */
  eventType: string
  userIds?: string[]
  agentIds?: string[]
  status: string
  /** 毫秒。异步 add 还没跑完时是 null（页面留空），不是 0。 */
  duration?: number | null
  /** 模型 token。上游没有回报时是 undefined，页面留空。 */
  requestTokens?: number
  responseTokens?: number
}

/** 调用日志详情。`requestBody` / `responseBody` 是 JSON 字符串，前端要二次 parse */
export interface LogDetail extends Omit<RequestLog, 'userIds' | 'agentIds'> {
  traceId?: string
  requestId?: string
  userId?: string
  agentId?: string
  requestCode?: number
  responseCode?: number
  requestBody?: string
  responseBody?: string
  /** 上游 add 回报的 LLM 调用次数；没有回报时不下发 */
  llmCalls?: number
}

/* ------------------------------------------------------------ 记忆 */

export interface Memory {
  memoryId: string
  memoryContent: string
  /** user | agent | public */
  subjectType: string
  externalUserId: string
  createTime: string
  /** 上游的 memory_type 原文（LongTermMemory / UserMemory / Context / InsightMemory …）。
   *  「事件记忆」页签里混着 Context 与 InsightMemory 两种，列表要靠它区分。 */
  memoryType?: string
  /** skill_mem 专有 */
  skillName?: string
  skillUrl?: string
  /** profile_mem 专有 */
  profileTemplateId?: string
  profileInstanceId?: string
}

/* ------------------------------------------------------------ 知识库 */

export interface KnowledgeBase {
  kbId: string
  knowledgebaseName: string
  knowledgebaseDescription?: string
  projectIds?: string[]
  fileCount?: number
  totalSize?: number
  createTime?: string
  updateTime?: string
}

/** 知识库文件条目（上游 public_file_view 的投影） */
export interface KnowledgeFile {
  id: string
  fileId: string
  knowledgebaseId: string
  name: string
  type?: string
  status?: string
  size: number
  sizeMB?: number
  createTime?: string
}

/* ------------------------------------------------------------ 画像模板 */

export interface ProfileTemplate {
  templateId: string
  templateName: string
  bindingCount?: number
  updatedAt?: string
  [k: string]: unknown
}

/* ------------------------------------------------------------ 用量 */

export interface UsageDailyStat {
  date: string
  addMessage?: { calls?: number; totalTokens?: number }
  searchMemory?: { calls?: number; totalTokens?: number }
  chat?: { requestTokens?: number; responseTokens?: number; totalTokens?: number }
  extractMemory?: { requestTokens?: number; responseTokens?: number; totalTokens?: number }
  rerank?: { requestTokens?: number; totalTokens?: number }
}

/* ------------------------------------------------------------ 运行信息 */

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
  /** 鉴权是否生效。**不是**给人看的文案（那是 `auth`），是给程序判断用的 */
  authEnabled?: boolean
  /** `page` = 控制台登录页；`basic` = HTTP Basic；`external` = 零信任网关注入身份 */
  authMode?: 'page' | 'basic' | 'external'
}

/** 当前登录主体（`/api/auth/me`） */
export interface Account {
  /** 账号 ID；管理 Token 没有账号身份时为空 */
  accountId?: string
  username: string
  displayName: string
  platformAdmin: boolean
  currentProjectId: string
  projects: { id: string; name: string; role: string; kind?: 'team' | 'personal' }[]
}

/* ------------------------------------------------------------ 模型 */

/** 上游配置里真实生效的一个模型 */
export interface ModelRecord {
  /** 在记忆链路里的位置：记忆读取 / 记忆写入 / 向量化 / 重排 */
  role: string
  model: string
  /** 关键参数（提供方主机名 · 维度 / 后端） */
  spec: string
  /** 取自上游 ConfigMap 的哪个键，排障时用来核对 */
  source: string
  group: 'memory' | 'chat'
}

/* ------------------------------------------------------------ 图谱 */

export type GraphLinkKind = 'session' | 'parent' | 'merged' | 'derived'

export interface GraphNode {
  id: string
  /** 记忆正文的截断（≤120 字）。空串表示这条没正文，画布上退回显示 id 前缀 */
  label: string
  /** `label` 被截断过（BFF 现算的，不是靠「以 … 结尾」猜的）。
   *  图谱响应里只带截断正文——全库正文是 MB 级，这个接口要一次给完整张图。
   *
   *  ⚠️ 前端别用「label 以 `…` 结尾」代替这个字段：正文自己以省略号结尾时会误判成
   *  截断，点「展开」什么都不变，看着就是个坏按钮。 */
  labelTruncated: boolean
  memoryType: string
  createdAt: string
  /** 空串 = 没有会话归属 */
  sessionId: string
  /** 簇 id：`session:<id>` 或 `orphan:<序号>` */
  clusterId: string
  userId: string
  /** 这条记忆归纳自哪些记忆（上游 `source_memory_ids`）。洞察记忆才有，其余为空数组。
   *  它在上游是**节点属性不是边**，画布上的 `derived` 连线由 BFF 补出来。 */
  sourceIds: string[]
}

export interface GraphLink {
  source: string
  target: string
  /** `session` 是按 session_id 聚合出来的星形连线，不是图库里存的边 */
  kind: GraphLinkKind
}

export interface MemoryGraph {
  nodes: GraphNode[]
  links: GraphLink[]
  /** 实际生效的租户（BFF 回显，便于确认画的是哪个租户） */
  tenant?: string
  stats: {
    nodes: number
    links: number
    sessions: number
    /** 规模 ≥3、会画成带标签区域的会话数 */
    clusters: number
    orphans: number
    /** 撞到节点上限被截断了 */
    truncated: boolean
    types: { name: string; count: number }[]
  }
}
