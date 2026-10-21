import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** 后端代理：默认本地 mock（pnpm mock），也可以指向已部署的后端。
 *
 *  看真实数据只改这一处，两条路都行：
 *    .env.local:  MOCK_ORIGIN=http://<后端地址>
 *    命令行:      MOCK_ORIGIN=http://<后端地址> pnpm dev
 *
 *  `/__login`、`/__logout` 也一起代理：后端若开登录页鉴权，只代理 /api 会让浏览器
 *  打不开登录页、拿不到会话 cookie，接口全线 401；退出登录也会落到本地路由。 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = process.env.MOCK_ORIGIN || env.MOCK_ORIGIN || 'http://localhost:5280'
  const proxy = {
    '/api': { target, changeOrigin: true },
    '/__login': { target, changeOrigin: true },
    '/__logout': { target, changeOrigin: true },
  }

  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5274, proxy },
    preview: { port: 5275, proxy },
  }
})
