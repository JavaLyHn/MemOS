/** 所有外部地址与后端入口，部署时用环境变量覆盖。
 *  VITE_SERVICE_BASE     记忆服务对外地址
 *  VITE_API_BASE         后端 origin，留空 = 同源（接口路径自带 /api 前缀）
 *  VITE_TECH_CONFIG_URL  模型清单静态目录
 */

const env = import.meta.env

export const SERVICE_BASE: string = (env.VITE_SERVICE_BASE || 'http://localhost:8003').replace(/\/+$/, '')

export const API_BASE: string = (env.VITE_API_BASE || '').replace(/\/+$/, '')

export const TECH_CONFIG_URL: string = (env.VITE_TECH_CONFIG_URL || '/tech-config').replace(/\/+$/, '')

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
