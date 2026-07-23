// CodingDashboardDetail 视图测试（2 场景：有数据 + 返回跳总览）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import CodingDashboardDetail from './CodingDashboardDetail.vue'
import type { CodingFetchLike } from '@/api/coding_dashboard'
import type { CodingDetail, T12Metrics } from '@/types/api'

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

const fakeDetail: CodingDetail = {
  run_id: 'crun-1',
  task: 'Write a function add(a, b) that returns a + b',
  test_file: 'tests/test_add.py',
  iteration_count: 1,
  success: true,
  started_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:00:04Z',
  patches: [
    {
      patch_id: 'p-1',
      iteration: 1,
      file_path: 'mymod.py',
      hunks_proposed: 1,
      hunks_applied: 1,
      diff: '@@ -1,1 +1,1 @@\n-# empty\n+def add(a, b): return a + b\n',
      ts: '2026-07-23T00:00:02Z'
    }
  ],
  test_runs: [
    {
      iteration: 1,
      tests_total: 1,
      tests_passed: 1,
      tests_failed: 0,
      compile_passed: true,
      raw_output: '1 passed in 0.1s',
      ts: '2026-07-23T00:00:04Z'
    }
  ]
}

const fakeT12Metrics: T12Metrics = {
  task_completion_rate: { rate: 1.0, passed: 1, total: 1 },
  tests_passed_rate: { rate: 1.0, passed: 1, total: 1 },
  patch_quality: { rate: 1.0, hunks_applied: 1, hunks_proposed: 1 },
  iteration_count: { value: 1, iterations: 1 },
  time_to_first_pass_s: { avg_s: 4.0, first_pass_iterations: 1 },
  self_recovery_rate: { rate: 0.0, auto_recovered: 0, total_failures: 0 },
  compile_success_rate: { rate: 1.0, compile_passed: 1, total_runs: 1 },
  test_growth_rate: { rate: 0.0, tests_added: 0, iterations: 1 }
}

describe('CodingDashboardDetail view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('有数据：渲染 summary 5 tile + iteration badge + patch diff + test history + metrics', async () => {
    const { fn, urls } = makeFetch({
      '/api/coding/runs/crun-1': { status: 200, body: fakeDetail },
      '/api/coding/runs/crun-1/metrics': { status: 200, body: fakeT12Metrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/coding/crun-1')
      await router.isReady()
      const wrapper = mount(CodingDashboardDetail, {
        props: { runId: 'crun-1' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="coding-detail"]').exists()).toBe(true)
      // 2 个 endpoint
      expect(urls).toContain('/api/coding/runs/crun-1')
      expect(urls).toContain('/api/coding/runs/crun-1/metrics')
      // task 截断 + test_file + success
      expect(wrapper.find('[data-testid="coding-detail-task"]').text()).toContain('Write a function')
      expect(wrapper.find('[data-testid="coding-detail-test-file"]').text()).toContain(
        'tests/test_add.py'
      )
      expect(wrapper.find('[data-testid="coding-detail-success"]').text()).toContain('✓')
      // iteration badge 1 → green
      expect(wrapper.find('[data-testid="iter-badge-1"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="iter-badge-1"]').attributes('data-level')).toBe('green')
      // patch diff viewer
      expect(wrapper.find('[data-testid="patch-diff-viewer"]').exists()).toBe(true)
      // test history
      expect(wrapper.find('[data-testid="test-history-timeline"]').exists()).toBe(true)
      // 8 指标列表
      expect(wrapper.find('[data-testid="coding-detail-metrics"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('返回按钮：跳 coding 总览', async () => {
    const { fn } = makeFetch({
      '/api/coding/runs/crun-1': { status: 200, body: fakeDetail },
      '/api/coding/runs/crun-1/metrics': { status: 200, body: fakeT12Metrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/coding/crun-1')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(CodingDashboardDetail, {
        props: { runId: 'crun-1' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      await wrapper.find('[data-testid="coding-back-btn"]').trigger('click')
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({ name: 'coding-dashboard' })
    } finally {
      global.fetch = orig
    }
  })
})
