// CodingDashboard 总览视图测试（2 场景：空 / 有数据 + 行点击跳详情）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import CodingDashboard from './CodingDashboard.vue'
import type { CodingFetchLike } from '@/api/coding_dashboard'
import type { CodingRunItem, CodingSummary } from '@/types/api'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/dashboard/coding',
        name: 'coding-dashboard',
        component: { template: '<div/>' }
      },
      {
        path: '/dashboard/coding/:runId',
        name: 'coding-dashboard-detail',
        component: { template: '<div/>' }
      }
    ]
  })
}

function makeFetch(
  responses: Record<string, { status: number; body: unknown }>
): { fn: CodingFetchLike; urls: string[] } {
  const urls: string[] = []
  const fn: CodingFetchLike = async (input) => {
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

const fakeSummary: CodingSummary = {
  run_count: 5,
  task_completion_rate: 0.8,
  tests_passed_rate: 0.9,
  avg_iteration_count: 1.5,
  avg_time_to_first_pass_s: 4.0,
  self_recovery_rate: 0.7
}

const fakeRuns: CodingRunItem[] = [
  {
    run_id: 'crun-1',
    task: 'add',
    test_file: 'tests/test_add.py',
    iteration_count: 1,
    success: true,
    started_at: '2026-07-23T00:00:00Z',
    finished_at: '2026-07-23T00:00:04Z'
  }
]

describe('CodingDashboard view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('空数据：summary 全 0 + runs 显示 empty', async () => {
    const { fn } = makeFetch({
      '/api/coding/summary': {
        status: 200,
        body: {
          run_count: 0,
          task_completion_rate: 0,
          tests_passed_rate: 0,
          avg_iteration_count: 0,
          avg_time_to_first_pass_s: 0,
          self_recovery_rate: 0
        }
      },
      '/api/coding/runs?limit=20&offset=0': {
        status: 200,
        body: { total: 0, runs: [] }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/coding')
      await router.isReady()
      const wrapper = mount(CodingDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="coding-dashboard-overview"]').exists()).toBe(true)
      // 全 0 时显示 0.0% / 0.0
      expect(wrapper.find('[data-testid="coding-summary-card"]').text()).toContain('0.0%')
      expect(wrapper.find('[data-testid="cruns-empty"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('有数据：渲染 summary + runs + 点击行跳 run 详情', async () => {
    const { fn } = makeFetch({
      '/api/coding/summary': { status: 200, body: fakeSummary },
      '/api/coding/runs?limit=20&offset=0': {
        status: 200,
        body: { total: 1, runs: fakeRuns }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/coding')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(CodingDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="cmetric-completion"]').text()).toContain(
        '80.0%'
      )
      expect(wrapper.findAll('[data-testid^="cruns-row-"]')).toHaveLength(1)
      await wrapper.find('[data-testid="cruns-row-crun-1"]').trigger('click')
      expect(pushSpy).toHaveBeenCalled()
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({
        name: 'coding-dashboard-detail',
        params: { runId: 'crun-1' }
      })
    } finally {
      global.fetch = orig
    }
  })
})
