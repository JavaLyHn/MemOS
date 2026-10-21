/** 所有外部地址与后端入口，部署时用环境变量覆盖。
 *  VITE_SERVICE_BASE     记忆服务对外地址（不设则按当前访问地址推）
 *  VITE_API_BASE         后端 origin，留空 = 同源（接口路径自带 /api 前缀）
 */

const env = import.meta.env

/** 记忆服务（MCP 落地页）监听的端口。 */
const SERVICE_PORT = '8003'

/** 记忆服务地址的**默认值**：跟着控制台自己的访问地址走。
 *
 *  ⚠️ 这里原来写死 `http://localhost:8003`。它只在开发机成立，一旦部署就全错：
 *  运维从部署地址打开控制台，文档页里的「服务地址」和侧边栏的「服务落地页」
 *  却把人往**他自己电脑的 8003 端口**送——浏览器要么连不上，要么连上的是本地别的东西。
 *  2026-10-19 用户报的就是这个。
 *
 *  改成按 `location` 推：控制台在哪个主机上，记忆服务就在同一主机的 8003。
 *  这样开发（前端 5274 → 服务 8003）和部署（控制台端口 → 服务 8003）
 *  **都不需要构建参数**，也就不会再有人忘记传。
 *
 *  ⚠️ 注释里**不要写具体的部署地址**：这个仓库是公开的。
 *
 *  两者不同主机时用 `VITE_SERVICE_BASE` 覆盖。 */
function defaultServiceBase(): string {
  if (typeof location === 'undefined' || !location.hostname) return `http://localhost:${SERVICE_PORT}`
  return `${location.protocol}//${location.hostname}:${SERVICE_PORT}`
}

export const SERVICE_BASE: string = (env.VITE_SERVICE_BASE || defaultServiceBase()).replace(/\/+$/, '')

export const API_BASE: string = (env.VITE_API_BASE || '').replace(/\/+$/, '')

export const LINKS = {
  /** 服务落地页：MCP 地址与接入说明都在上面 */
  home: `${SERVICE_BASE}/`,
  /** 服务健康检查，返回 JSON */
  health: `${SERVICE_BASE}/health`,
  /** MCP 接入地址 */
  mcp: `${SERVICE_BASE}/mcp`,
  /** 控制台内置文档页 */
  docs: '/cn/docs',
  about: '/cn/about',
} as const
