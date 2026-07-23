import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 单独的 vitest 配置：jsdom 环境 + Vue SFC 处理
// 与 vite.config.ts 解耦，避免在 Vite dev server 加载 vitest 依赖
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.{spec,test}.{ts,tsx}'],
    exclude: ['node_modules', 'dist'],
    // ECharts 在 jsdom 下渲染开销大；测试只验证 option 透传，不真实画图
    // （ChartWidget 的真实渲染由 E2E 验证）
  },
})
