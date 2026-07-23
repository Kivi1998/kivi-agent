// DashboardCaseDetail 视图测试（2 场景：有 trace / 空 trace + 工具 + RAG 渲染）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import DashboardCaseDetail from './DashboardCaseDetail.vue'
import type { FetchLike } from '@/api/dashboard'
import type { TracesResponse } from '@/types/api'

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
} {
  const fn: FetchLike = async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return { fn }
}

const fakeTraces: TracesResponse = {
  run_id: 'run-1',
  traces: [
    {
      case_id: 'case-1',
      events: [
        { type: 'route.decided', ts: '2026-07-23T00:00:00Z', data: { intent: 'rag' } },
        { type: 'run.finished', ts: '2026-07-23T00:00:01Z', data: { success: true } }
      ],
      tool_calls: [
        {
          tool_name: 'web_search',
          started_at: '2026-07-23T00:00:00.500Z',
          finished_at: '2026-07-23T00:00:00.900Z',
          success: true
        }
      ],
      rag_sources: [{ id: 'src-1' }, { id: 'src-2' }]
    },
    {
      case_id: 'case-2',
      events: [],
      tool_calls: [],
      rag_sources: []
    }
  ]
}

describe('DashboardCaseDetail view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('有 trace：渲染 timeline + tools 列表 + RAG 列表', async () => {
    const { fn } = makeFetch({
      '/api/dashboard/runs/run-1/traces?case_id=case-1': {
        status: 200,
        body: fakeTraces
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/runs/run-1/cases/case-1')
      await router.isReady()
      const wrapper = mount(DashboardCaseDetail, {
        props: { runId: 'run-1', caseId: 'case-1' },
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="case-detail"]').exists()).toBe(true)
      // TraceTimeline 渲染
      expect(wrapper.find('[data-testid="trace-timeline"]').exists()).toBe(true)
      // 工具调用
      expect(wrapper.find('[data-testid="side-tool-web_search"]').exists()).toBe(true)
      // RAG 引用
      expect(wrapper.findAll('[data-testid^="side-rag-"]')).toHaveLength(2)
    } finally {
      global.fetch = orig
    }
  })

  it('无 trace：显示 "未找到该 case 的事件流" empty', async () => {
    // 返回 traces[] 不含 case-1
    const { fn } = makeFetch({
      '/api/dashboard/runs/run-1/traces?case_id=case-missing': {
        status: 200,
        body: { run_id: 'run-1', traces: [] }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/runs/run-1/cases/case-missing')
      await router.isReady()
      const wrapper = mount(DashboardCaseDetail, {
        props: { runId: 'run-1', caseId: 'case-missing' },
        global: { plugins: [router], stubs: { echarts: VChartStub } }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="case-empty"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })
})
