import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Vite + Vue 3 配置：仅支持 apps/web-chat/ 单 SPA，不做 PWA / SSR
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // WT-E1 联调时由主控在 vite.config.ts 里加 /api 与 /ws 代理；本 WT 不引入
    },
  },
})
