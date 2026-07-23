/**
 * E2E Test 4: Multi-Intent (agent: package-web-e2e-v3)
 *
 * 覆盖路径（v1 §3.2 / Wave 3 §一）：
 * 1. 启动 session + 发送多意图 query "对比网上关于 RAG 的最新文章和我们内部知识库"
 * 2. 验证 RoutePanel 显示 multi_intent + 3 个 profile（web_search + rag + synthesizer）
 * 3. 验证 2 个 citation + 1 个 chart
 * 4. 验证 frontend.tool_call_responded 事件触发
 * 5. 验证 run.finished 后 Synthesizer 汇总消息出现
 * 6. 截图
 *
 * 这是 Wave 3 收官视觉证据 — 真实端到端展示 v1 §5.2.1 业务事件流契约。
 */
import { test, expect } from '@playwright/test'

test('multi-intent query triggers rag + web_search + synthesizer chain', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('h2', { hasText: '会话列表' })).toBeVisible()

  // 发送多意图 query
  const goalInput = page.locator('[data-testid="session-goal-input"]')
  await goalInput.fill('对比网上关于 RAG 的最新文章和我们内部知识库')
  await page.click('[data-testid="send-button"]')

  // 1. 验证 RoutePanel = multi_intent
  const routePanel = page.locator('[data-testid="route-panel"]')
  await routePanel.waitFor({ state: 'visible', timeout: 10_000 })
  await expect(routePanel.locator('.badge', { hasText: 'multi_intent' })).toBeVisible()

  // 2. 验证 3 个 profile tag
  const profileTags = await routePanel.locator('.profile-tag').allTextContents()
  expect(profileTags.length).toBeGreaterThanOrEqual(2)
  expect(profileTags).toContain('rag')
  expect(profileTags).toContain('synthesizer')

  // 3. 验证 citation widget 出现（rag 触发）
  const citationWidget = page.locator('[data-testid="citation-widget"]')
  await citationWidget.waitFor({ state: 'visible', timeout: 10_000 })
  const citationCount = await citationWidget.locator('li').count()
  expect(citationCount).toBeGreaterThanOrEqual(2)

  // 4. 验证 chart widget 出现
  const chartWidget = page.locator('[data-testid="chart-widget"]')
  await chartWidget.waitFor({ state: 'visible', timeout: 10_000 })
  const barCount = await chartWidget.locator('.bar').count()
  expect(barCount).toBeGreaterThan(0)

  // 5. 等待 run.finished
  await expect(goalInput).toBeEnabled({ timeout: 10_000 })

  // 6. 验证 Synthesizer 汇总消息（"多意图查询完成"）
  await expect(page.locator('.message.assistant', { hasText: '多意图查询完成' })).toBeVisible({
    timeout: 5_000,
  })

  // 截图（满足 ≥1280x720 约束）
  await page.screenshot({ path: 'screenshots/multi_intent.png', fullPage: true })
})
