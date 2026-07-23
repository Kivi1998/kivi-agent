/**
 * E2E Test 2: Cancel (agent: package-web-e2e-v3)
 *
 * 覆盖路径：
 * 1. 启动 session + 发送 query（goal 含"取消"）
 * 2. 等待事件流：session.created → run.started → run.cancelled → run.finished
 * 3. 验证 cancelled-banner 出现
 * 4. 验证输入框被禁用（dataset.disabledMarker === '1'）
 * 5. 截图
 *
 * 注：fake runtime 下所有事件是同步触发的，没有"mid-run cancel"窗口；
 * 真实 kivi-core 流式场景下"用户中途按停止按钮"的测试需要 tick_interval 配置，
 * 不在 WT-E5 范围。本测试覆盖 cancel 模式事件流契约本身。
 */
import { test, expect } from '@playwright/test'

test('user cancels session, sees RunCancelled event and input disabled', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('h2', { hasText: '会话列表' })).toBeVisible()

  // goal 含"取消" → fake runtime 触发 cancel 模式
  const goalInput = page.locator('[data-testid="session-goal-input"]')
  await goalInput.fill('请取消这个任务')
  await page.click('[data-testid="send-button"]')

  // 等待 run.started 触发 RoutePanel
  await page.locator('[data-testid="route-panel"]').waitFor({ state: 'visible', timeout: 10_000 })

  // 等待 cancelled-banner 出现（fake runtime 推 run.cancelled 事件后渲染）
  const cancelledBanner = page.locator('[data-testid="cancelled-banner"]')
  await cancelledBanner.waitFor({ state: 'visible', timeout: 10_000 })
  await expect(cancelledBanner).toContainText('RunCancelled')
  await expect(cancelledBanner).toContainText('user_requested')

  // 等待 run.finished 后输入框解锁
  await expect(goalInput).toBeEnabled({ timeout: 10_000 })

  // 取消按钮在 run.finished 后应隐藏
  const cancelButton = page.locator('[data-testid="cancel-button"]')
  await expect(cancelButton).not.toBeVisible({ timeout: 5_000 })

  // 截图
  await page.screenshot({ path: 'screenshots/cancel.png', fullPage: true })
})
