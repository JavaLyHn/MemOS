import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** mock 后端是独立进程（server/mock/server.ts，pnpm mock），这里只做代理。
 *  接真后端时把 VITE_API_BASE 指过去，连代理都不用改。 */
const MOCK = process.env.MOCK_ORIGIN || 'http://localhost:5280'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5274,
    proxy: { '/api': { target: MOCK, changeOrigin: true } },
  },
  preview: {
    port: 5275,
    proxy: { '/api': { target: MOCK, changeOrigin: true } },
  },
})
