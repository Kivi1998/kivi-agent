/**
 * E2E Test 3: Reconnect (agent: package-web-e2e-v3)
 *
 * 覆盖路径（v1 §3 / Wave 3 §三）：
 * 1. 启动 session + 发送 query
 * 2. 模拟 WS 断线（page.context().setOffline(true)）→ 浏览器触发 offline 事件 → UI 显示 reconnecting-status
 * 3. 模拟网络恢复（setOffline(false)）→ UI 自动重连 → connection-status 回到 connected
 * 4. 截图
 *
 * 注：test_page.html 监听 window 'offline' 事件并把 connection-status 切到 reconnecting；
 * 'online' 事件触发自动重连。
 */
import { test, expect } from '@playwright/test'

test('WS disconnects, auto-reconnects, events continue', async ({ page, context }) => {
  await page.goto('/')

  // 启动 session
  const goalInput = page.locator('[data-testid="session-goal-input"]')
  await goalInput.fill('对比网上关于 RAG 的最新文章')
  await page.click('[data-testid="send-button"]')

  // 等待连接建立
  await expect(page.locator('[data-testid="connection-status"]')).toHaveAttribute(
    'data-state',
    'connected',
    { timeout: 10_000 }
  )
  // 等待 RoutePanel 出现（事件流开始）
  await page.locator('[data-testid="route-panel"]').waitFor({ state: 'visible', timeout: 10_000 })

  // 模拟断线
  await context.setOffline(true)
  // browser 派发 offline 事件 → test_page.html 把状态切到 reconnecting
  await expect(page.locator('[data-testid="connection-status"]')).toHaveAttribute(
    'data-state',
    'reconnecting',
    { timeout: 5_000 }
  )
  // reconnecting-status banner 也应可见
  await expect(page.locator('[data-testid="reconnecting-status"]')).toBeVisible({ timeout: 5_000 })

  // 恢复网络
  await context.setOffline(false)
  // online 事件触发重连（test_page.html 调 connectWS）
  await expect(page.locator('[data-testid="connection-status"]')).toHaveAttribute(
    'data-state',
    'connected',
    { timeout: 15_000 }
  )

  // 等待 run.finished → 输入框解锁（验证事件流还在工作）
  await expect(goalInput).toBeEnabled({ timeout: 15_000 })

  // 截图
  await page.screenshot({ path: 'screenshots/reconnect.png', fullPage: true })
})
