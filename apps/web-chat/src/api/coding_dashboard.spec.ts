// coding dashboard API 单元测试（9 场景：5 端点 + computeCodingSummaryFromRuns + 错误处理 + 边界）
import { describe, it, expect, vi } from 'vitest'
import {
  createCodingDashboardApi,
  computeCodingSummaryFromRuns,
  type CodingFetchLike
} from './coding_dashboard'
import type {
  CodingDetail,
  CodingRunListResponse,
  CodingRunItem,
  CodingSummary,
  PatchRecord,
  T12Metrics,
  TestRunRecord
} from '@/types/api'

/** 测试用 fetch mock：根据 URL 分发响应 */
function makeFetchMock(
  responses: Record<string, { status: number; body: unknown }>
): {
  fn: CodingFetchLike
  calls: Array<{ url: string; init?: RequestInit }>
} {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn: CodingFetchLike = async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    calls.push({ url, init })
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), {
        status: 404
      })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return { fn, calls }
}

const fakeSummary: CodingSummary = {
  run_count: 6,
  task_completion_rate: 0.83,
  tests_passed_rate: 0.9,
  avg_iteration_count: 2.1,
  avg_time_to_first_pass_s: 8.5,
  self_recovery_rate: 0.7
}

const fakeRunItem: CodingRunItem = {
  run_id: 'crun-1',
  task: 'Write a function add(a, b) that returns a + b',
  test_file: 'tests/test_add.py',
  iteration_count: 2,
  success: true,
  started_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:00:08Z'
}

const fakeRunList: CodingRunListResponse = {
  total: 2,
  runs: [
    fakeRunItem,
    {
      ...fakeRunItem,
      run_id: 'crun-2',
      iteration_count: 3,
      success: false,
      started_at: '2026-07-22T00:00:00Z',
      finished_at: null
    }
  ]
}

const fakePatches: PatchRecord[] = [
  {
    patch_id: 'p-1',
    iteration: 1,
    file_path: 'mymod.py',
    hunks_proposed: 1,
    hunks_applied: 1,
    diff: '@@ -1,1 +1,1 @@\n-# empty\n+def add(a, b): return a + b\n',
    ts: '2026-07-23T00:00:02Z'
  }
]

const fakeTestRuns: TestRunRecord[] = [
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

const fakeRunDetail: CodingDetail = {
  run_id: 'crun-1',
  task: 'Write a function add(a, b) that returns a + b',
  test_file: 'tests/test_add.py',
  iteration_count: 1,
  success: true,
  started_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:00:08Z',
  patches: fakePatches,
  test_runs: fakeTestRuns
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

describe('createCodingDashboardApi', () => {
  it('getCodingSummary GET /coding/summary returns summary', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/coding/summary': { status: 200, body: fakeSummary }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const result = await api.getCodingSummary()
    expect(result).toEqual(fakeSummary)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('/api/coding/summary')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('listCodingRuns GET /coding/runs?limit=&offset= unwraps runs[]', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/coding/runs?limit=20&offset=0': {
        status: 200,
        body: fakeRunList
      }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const result = await api.listCodingRuns(20, 0)
    expect(result.total).toBe(2)
    expect(result.runs).toHaveLength(2)
    expect(result.runs[0]?.run_id).toBe('crun-1')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getCodingRun GET /coding/runs/:runId returns detail with patches+test_runs', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/coding/runs/crun-1': { status: 200, body: fakeRunDetail }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const detail = await api.getCodingRun('crun-1')
    expect(detail.run_id).toBe('crun-1')
    expect(detail.patches).toHaveLength(1)
    expect(detail.test_runs).toHaveLength(1)
    expect(detail.patches[0]?.hunks_applied).toBe(1)
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getCodingRun encodes special characters in runId', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/coding/runs/crun%2Fwith%2Fslash': {
        status: 200,
        body: { ...fakeRunDetail, run_id: 'crun/with/slash' }
      }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    await api.getCodingRun('crun/with/slash')
    expect(calls[0]?.url).toBe('/api/coding/runs/crun%2Fwith%2Fslash')
  })

  it('getCodingPatches GET /coding/runs/:runId/patches returns patch list', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/coding/runs/crun-1/patches': {
        status: 200,
        body: fakePatches
      }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const ps = await api.getCodingPatches('crun-1')
    expect(ps).toHaveLength(1)
    expect(ps[0]?.iteration).toBe(1)
    expect(ps[0]?.file_path).toBe('mymod.py')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getCodingMetrics GET /coding/runs/:runId/metrics returns T12Metrics', async () => {
    const { fn } = makeFetchMock({
      '/api/coding/runs/crun-1/metrics': {
        status: 200,
        body: fakeT12Metrics
      }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const m = await api.getCodingMetrics('crun-1')
    expect(m.task_completion_rate.rate).toBe(1.0)
    expect(m.tests_passed_rate.passed).toBe(1)
    expect(m.patch_quality.hunks_applied).toBe(1)
  })

  it('非 2xx 响应抛错且消息含状态码', async () => {
    const fn: CodingFetchLike = vi.fn(async () =>
      new Response('boom', { status: 502, statusText: 'Bad Gateway' })
    ) as unknown as CodingFetchLike
    const api = createCodingDashboardApi({ fetchImpl: fn })
    await expect(api.getCodingSummary()).rejects.toThrow(/502/)
  })

  it('暴露内部 request helper（advanced 用）', async () => {
    const { fn } = makeFetchMock({
      '/api/coding/custom-path': { status: 200, body: { ok: true } }
    })
    const api = createCodingDashboardApi({ fetchImpl: fn })
    const r = await api.request<{ ok: boolean }>('/coding/custom-path')
    expect(r.ok).toBe(true)
  })
})

describe('computeCodingSummaryFromRuns', () => {
  it('空数组：run_count=0 + completion=0 + iter=0', () => {
    const r = computeCodingSummaryFromRuns([])
    expect(r.run_count).toBe(0)
    expect(r.task_completion_rate).toBe(0)
    expect(r.avg_iteration_count).toBe(0)
  })

  it('3 个 run：2 成功 / avg iter = (1+2+3)/3', () => {
    const r = computeCodingSummaryFromRuns([
      { success: true, iteration_count: 1 },
      { success: true, iteration_count: 2 },
      { success: false, iteration_count: 3 }
    ])
    expect(r.run_count).toBe(3)
    expect(r.task_completion_rate).toBeCloseTo(2 / 3, 5)
    expect(r.avg_iteration_count).toBeCloseTo(2, 5)
  })
})
