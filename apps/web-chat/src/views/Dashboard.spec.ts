// Dashboard 总览视图测试（2 场景：空 / 有数据 + 行点击跳详情）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import Dashboard from './Dashboard.vue'
import type { FetchLike } from '@/api/dashboard'
import type { RunSummary, Summary } from '@/types/api'

/** VChart 占位 stub：避免 ECharts 在 jsdom 里真实渲染触发 zrender Canvas 异常 */
const VChartStub = {
  name: "echarts",
  props: ['option'],
  template: '<div data-testid="vchart-stub" />'
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/dashboard',
        name: 'dashboard',
        component: { template: '<div/>' }
      },
      {
        path: '/dashboard/runs/:runId',
        name: 'dashboard-run-detail',
        component: { template: '<div/>' }
      }
    ]
  })
}

function makeFetch(responses: Record<string, { status: number; body: unknown }>): {
  fn: FetchLike
  urls: string[]
} {
  const urls: string[] = []
  const fn: FetchLike = async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    urls.push(url)
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return { fn, urls }
}

const fakeSummary: Summary = {
  case_count: 10,
  success_rate: 0.7,
  avg_latency_s: 2.5,
  total_tokens: 5000,
  total_cost_usd: 0.5
}

const fakeRuns: RunSummary[] = [
  {
    run_id: 'run-1',
    started_at: '2026-07-23T00:00:00Z',
    case_count: 5,
    success_count: 4
  }
]

describe('Dashboard view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('空数据：summary 全 0 时 metric 渲染 0 + RunsList 显示 empty', async () => {
    const { fn } = makeFetch({
      '/api/dashboard/summary': {
        status: 200,
        body: { case_count: 0, success_rate: 0, avg_latency_s: 0, total_tokens: 0, total_cost_usd: 0 }
      },
      '/api/dashboard/runs?limit=20&offset=0': { status: 200, body: { total: 0, runs: [] } }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard')
      await router.isReady()
      const wrapper = mount(Dashboard, {
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="dashboard-overview"]').exists()).toBe(true)
      // 全 0 时 SummaryCard 渲染 "0.0%" / "0.00s" / "0" / "$0.0000"
      expect(wrapper.find('[data-testid="summary-card"]').text()).toContain('0.0%')
      expect(wrapper.find('[data-testid="summary-card"]').text()).toContain('$0.0000')
      expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('有数据：渲染 summary metric + runs 表 + 点击行跳详情', async () => {
    const { fn } = makeFetch({
      '/api/dashboard/summary': { status: 200, body: fakeSummary },
      '/api/dashboard/runs?limit=20&offset=0': {
        status: 200,
        body: { total: 1, runs: fakeRuns }
      },
      '/api/dashboard/runs/run-1': {
        status: 200,
        body: { run_id: 'run-1', case_count: 5, success_count: 4, results: [] }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(Dashboard, {
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="metric-success-rate"]').text()).toContain(
        '70.0%'
      )
      expect(wrapper.findAll('[data-testid^="runs-row-"]')).toHaveLength(1)
      await wrapper.find('[data-testid="runs-row-run-1"]').trigger('click')
      expect(pushSpy).toHaveBeenCalled()
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({
        name: 'dashboard-run-detail',
        params: { runId: 'run-1' }
      })
    } finally {
      global.fetch = orig
    }
  })
})
