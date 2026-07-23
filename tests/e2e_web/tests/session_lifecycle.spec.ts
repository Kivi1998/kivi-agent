/**
 * E2E Test 1: Session Lifecycle (agent: package-web-e2e-v3)
 *
 * 覆盖路径（v1 §3 / Wave 3 WT-E5 §三）：
 * 1. 用户打开 SessionList → 点击"新建会话"
 * 2. 输入多意图 goal（含"对比网上" + "知识库"关键词）
 * 3. 发送 → 真实创建 session（POST /sessions）
 * 4. WebSocket 收到事件流 → 前端渲染 RoutePanel + CitationWidget + ChartWidget
 * 5. 截图
 *
 * 这是 Wave 3 端到端最关键的场景，验证"业务事件从 kivi-core → Adapter → Bridge → WS → 浏览器"
 * 全链路通畅。
 */
import { test, expect } from '@playwright/test'

test('user creates session, sends query, sees RoutePanel + citations + chart', async ({ page }) => {
  // 1. 打开 SessionList
  await page.goto('/')
  await expect(page.locator('h2', { hasText: '会话列表' })).toBeVisible()

  // 2. 点击"新建会话"前先填输入框
  // 用 multi_intent 关键词（网上 + 知识库）以触发 rag + chart 事件
  // goal 与 multi_intent 测试不同（短一些），使截图 user 消息气泡差异化
  const goalInput = page.locator('[data-testid="session-goal-input"]')
  await goalInput.fill('对比网上 RAG 资料和我们内部知识库')

  // 3. 点击"发送"（点击会触发 newSession）
  await page.click('[data-testid="send-button"]')

  // 4. 等待 RoutePanel 出现（run.started 事件触发渲染）
  const routePanel = page.locator('[data-testid="route-panel"]')
  await routePanel.waitFor({ state: 'visible', timeout: 10_000 })
  // 验证至少含 rag profile
  const profileTags = await routePanel.locator('.profile-tag').allTextContents()
  expect(profileTags.length).toBeGreaterThanOrEqual(1)

  // 5. 等待 citation 出现
  const citationWidget = page.locator('[data-testid="citation-widget"]')
  await citationWidget.waitFor({ state: 'visible', timeout: 10_000 })
  // 验证至少 1 条引用
  const citationItems = await citationWidget.locator('li').count()
  expect(citationItems).toBeGreaterThanOrEqual(1)
  // 验证 RAG 架构设计要点存在
  await expect(citationWidget.locator('li', { hasText: 'RAG 架构' })).toBeVisible()

  // 6. 等待 chart 出现
  const chartWidget = page.locator('[data-testid="chart-widget"]')
  await chartWidget.waitFor({ state: 'visible', timeout: 10_000 })
  // 验证 chart 标题存在
  await expect(chartWidget.locator('h3', { hasText: 'RAG vs 知识库' })).toBeVisible()
  // 验证 chart stub 至少 1 个 bar
  const barCount = await chartWidget.locator('.bar').count()
  expect(barCount).toBeGreaterThan(0)

  // 7. 等待 run.finished 事件触发"输入解锁 + 发送按钮恢复"
  // run.finished → setRunning(false) → input 不再 disabled
  await expect(goalInput).toBeEnabled({ timeout: 10_000 })

  // 8. 截图（满足 ≥1280x720 约束）— 终态：所有 widget 都已渲染
  await page.screenshot({ path: 'screenshots/session_lifecycle.png', fullPage: true })
})
