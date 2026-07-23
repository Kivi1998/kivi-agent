// DashboardRunDetail 视图测试（2 场景：有数据 / 错误 + case 点击跳详情）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import DashboardRunDetail from './DashboardRunDetail.vue'
import type { FetchLike } from '@/api/dashboard'
import type { CaseEvalResult, MetricsReport, RunDetail } from '@/types/api'

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
      { path: '/dashboard', name: 'dashboard', component: { template: '<div/>' } },
      {
        path: '/dashboard/runs/:runId',
        name: 'dashboard-run-detail',
        component: { template: '<div/>' }
      },
      {
        path: '/dashboard/runs/:runId/cases/:caseId',
        name: 'dashboard-case-detail',
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

const fakeDetail: RunDetail = {
  run_id: 'run-1',
  case_count: 3,
  success_count: 2,
  results: [
    {
      case_id: 'case-1',
      success: true,
      latency_s: 1.0,
      final_answer: 'answer-1',
      tool_calls: [],
      rag_sources: []
    } as CaseEvalResult,
    {
      case_id: 'case-2',
      success: true,
      latency_s: 1.5,
      final_answer: 'answer-2',
      tool_calls: [],
      rag_sources: []
    } as CaseEvalResult,
    {
      case_id: 'case-3',
      success: false,
      latency_s: 2.0,
      final_answer: 'answer-3',
      tool_calls: [],
      rag_sources: []
    } as CaseEvalResult
  ]
}

const fakeMetrics: MetricsReport = {
  dataset_name: 'basic-routing-10cases',
  case_count: 3,
  generated_at: '2026-07-23T00:00:00Z',
  metrics: {
    task_success_rate: { rate: 0.6667, passed: 2, total: 3 },
    route_accuracy: { rate: 1.0, matched: 3, applicable: 3 },
    tool_selection_accuracy: {
      exact_match_rate: 0.5,
      contain_match_rate: 0.8,
      applicable: 3
    },
    rag_citation_accuracy: { rate: 0, matched: 0, applicable: 0 },
    avg_latency_seconds: { avg_s: 1.5, p50_s: 1.0, p95_s: 2.0, count: 3 },
    total_tokens: { input: 300, output: 600, cache_read: 0, total: 900 },
    total_cost_usd: { total_usd: 0.03, model: 'gpt-4o-mini', per_case_avg_usd: 0.01 }
  }
}

describe('DashboardRunDetail view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('有数据：渲染 case_count / success_count / 成功率 + CaseTable 行 + MetricsBar', async () => {
    const { fn } = makeFetch({
      '/api/dashboard/runs/run-1': { status: 200, body: fakeDetail },
      '/api/dashboard/runs/run-1/metrics': { status: 200, body: fakeMetrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/runs/run-1')
      await router.isReady()
      const wrapper = mount(DashboardRunDetail, {
        props: { runId: 'run-1' },
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="run-detail"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="run-case-count"]').text()).toContain('3')
      expect(wrapper.find('[data-testid="run-success-count"]').text()).toContain('2')
      // 2/3 = 66.7%
      expect(wrapper.find('[data-testid="run-success-rate"]').text()).toContain('66.7%')
      // 3 行 case
      expect(wrapper.findAll('[data-testid^="case-row-"]')).toHaveLength(3)
      // MetricsBar VChart stub 渲染
      expect(wrapper.find('[data-testid="metrics-chart"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('点击 case 行跳 case 详情', async () => {
    const { fn } = makeFetch({
      '/api/dashboard/runs/run-1': { status: 200, body: fakeDetail },
      '/api/dashboard/runs/run-1/metrics': { status: 200, body: fakeMetrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/runs/run-1')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(DashboardRunDetail, {
        props: { runId: 'run-1' },
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      await wrapper.find('[data-testid="case-row-case-2"]').trigger('click')
      expect(pushSpy).toHaveBeenCalled()
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({
        name: 'dashboard-case-detail',
        params: { runId: 'run-1', caseId: 'case-2' }
      })
    } finally {
      global.fetch = orig
    }
  })
})
