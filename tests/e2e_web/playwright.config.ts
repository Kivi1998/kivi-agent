/**
 * Playwright config (agent: package-web-e2e-v3).
 *
 * 设计说明：
 * - webServer 启动 2 个进程：FastAPI Gateway（注入 FakeAgentRuntime）+ 静态 test page 服务器
 * - 由于本 worktree (WT-E5) 不包含 apps/web-chat/（WT-E2 范围，尚未合并），
 *   使用 fixtures/test_page.html 作为最小测试页（与 Vue 组件 data-testid 契约一致）。
 *   等 WT-E2 合并后只需把 webServer[0] 切回 `cd ../../apps/web-chat && npm run dev` 即可。
 * - baseURL 固定 127.0.0.1:5173。
 * - viewport 1280x720，满足截图分辨率约束。
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    headless: true,
    viewport: { width: 1280, height: 720 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    // 绕过系统代理（防止 Chromium 用 http_proxy 拦截 127.0.0.1）
    launchOptions: {
      args: ['--no-proxy-server', '--proxy-bypass-list=*'],
    },
  },
  outputDir: './test-results',
  webServer: [
    // 静态 test page 服务器（CD 自身 5173 端口）
    {
      command: 'python3 fixtures/test_page_server.py',
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    // FastAPI Gateway（注入 FakeAgentRuntime）
    {
      // 使用 repo 根 .venv 的 python（fastapi 在 dev group 依赖里）
      command: '../../.venv/bin/python fixtures/gateway_runner.py',
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
      env: {
        KAMA_PORT: '7437',
        GATEWAY_PORT: '8000',
      },
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
