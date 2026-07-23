// dashboard API 单元测试（5 场景：5 端点 + computeSummaryFromCases + 错误处理）
import { describe, it, expect, vi } from 'vitest'
import {
  createDashboardApi,
  computeSummaryFromCases,
  type FetchLike
} from './dashboard'
import type {
  CaseEvalResult,
  MetricsReport,
  RunDetail,
  RunSummary,
  Summary,
  TracesResponse
} from '@/types/api'

/** 测试用 fetch mock：根据 URL 分发响应 */
function makeFetchMock(
  responses: Record<string, { status: number; body: unknown }>
): {
  fn: FetchLike
  calls: Array<{ url: string; init?: RequestInit }>
} {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn: FetchLike = async (input, init) => {
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

const fakeSummary: Summary = {
  case_count: 10,
  success_rate: 0.8,
  avg_latency_s: 2.5,
  total_tokens: 12345,
  total_cost_usd: 0.42
}

const fakeRuns: RunSummary[] = [
  {
    run_id: 'run-1',
    started_at: '2026-07-23T00:00:00Z',
    case_count: 5,
    success_count: 4
  },
  {
    run_id: 'run-2',
    started_at: null,
    case_count: 3,
    success_count: 2
  }
]

const fakeRunDetail: RunDetail = {
  run_id: 'run-1',
  case_count: 5,
  success_count: 4,
  results: [
    {
      case_id: 'case-1',
      success: true,
      latency_s: 1.2,
      input_tokens: 100,
      output_tokens: 200,
      cost_usd: 0.01
    },
    {
      case_id: 'case-2',
      success: false,
      latency_s: 3.4,
      input_tokens: 150,
      output_tokens: 250,
      cost_usd: 0.02
    }
  ]
}

const fakeMetrics: MetricsReport = {
  dataset_name: 'basic-routing-10cases',
  case_count: 5,
  generated_at: '2026-07-23T00:00:00Z',
  metrics: {
    task_success_rate: { rate: 0.8, passed: 4, total: 5 },
    route_accuracy: { rate: 1.0, matched: 5, applicable: 5 },
    tool_selection_accuracy: {
      exact_match_rate: 0.6,
      contain_match_rate: 0.8,
      applicable: 5
    },
    rag_citation_accuracy: { rate: 0.5, matched: 2, applicable: 4 },
    avg_latency_seconds: { avg_s: 2.3, p50_s: 1.5, p95_s: 4.0, count: 5 },
    total_tokens: { input: 500, output: 1000, cache_read: 100, total: 1600 },
    total_cost_usd: { total_usd: 0.05, model: 'gpt-4o-mini', per_case_avg_usd: 0.01 }
  }
}

const fakeTraces: TracesResponse = {
  run_id: 'run-1',
  traces: [
    {
      case_id: 'case-1',
      events: [
        { type: 'route.decided', ts: '2026-07-23T00:00:00Z', data: {} },
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
      rag_sources: []
    }
  ]
}

describe('createDashboardApi', () => {
  it('fetchSummary GET /dashboard/summary and returns summary', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/dashboard/summary': { status: 200, body: fakeSummary }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    const result = await api.fetchSummary()
    expect(result).toEqual(fakeSummary)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('/api/dashboard/summary')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('fetchRuns GET /dashboard/runs?limit=&offset= and unwraps runs[]', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/dashboard/runs?limit=20&offset=0': {
        status: 200,
        body: { total: 2, runs: fakeRuns }
      }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    const result = await api.fetchRuns(20, 0)
    expect(result.total).toBe(2)
    expect(result.runs).toHaveLength(2)
    expect(result.runs[0]?.run_id).toBe('run-1')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('fetchRunDetail GET /dashboard/runs/:runId and returns detail', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/dashboard/runs/run-1': { status: 200, body: fakeRunDetail }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    const detail = await api.fetchRunDetail('run-1')
    expect(detail.run_id).toBe('run-1')
    expect(detail.results).toHaveLength(2)
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('fetchMetrics GET /dashboard/runs/:runId/metrics returns MetricsReport', async () => {
    const { fn } = makeFetchMock({
      '/api/dashboard/runs/run-1/metrics': { status: 200, body: fakeMetrics }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    const m = await api.fetchMetrics('run-1')
    expect(m.dataset_name).toBe('basic-routing-10cases')
    expect(m.metrics.task_success_rate.rate).toBe(0.8)
    expect(m.metrics.total_tokens.total).toBe(1600)
  })

  it('fetchTraces 不带 caseId 时不带 query string', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/dashboard/runs/run-1/traces': { status: 200, body: fakeTraces }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    const t = await api.fetchTraces('run-1')
    expect(t.run_id).toBe('run-1')
    expect(t.traces).toHaveLength(1)
    expect(calls[0]?.url).toBe('/api/dashboard/runs/run-1/traces')
  })

  it('fetchTraces 带 caseId 时附加 ?case_id=...', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/dashboard/runs/run-1/traces?case_id=case-1': {
        status: 200,
        body: fakeTraces
      }
    })
    const api = createDashboardApi({ fetchImpl: fn })
    await api.fetchTraces('run-1', 'case-1')
    expect(calls[0]?.url).toBe('/api/dashboard/runs/run-1/traces?case_id=case-1')
  })

  it('非 2xx 响应抛错且消息含状态码', async () => {
    const fn: FetchLike = vi.fn(async () =>
      new Response('boom', { status: 500, statusText: 'Internal Server Error' })
    ) as unknown as FetchLike
    const api = createDashboardApi({ fetchImpl: fn })
    await expect(api.fetchSummary()).rejects.toThrow(/500/)
  })
})

describe('computeSummaryFromCases', () => {
  it('空数组：所有字段为 0', () => {
    const result = computeSummaryFromCases([])
    expect(result.case_count).toBe(0)
    expect(result.success_rate).toBe(0)
    expect(result.avg_latency_s).toBe(0)
    expect(result.total_tokens).toBe(0)
    expect(result.total_cost_usd).toBe(0)
  })

  it('5 个 case：正确算 success_rate / avg_latency / total_tokens / total_cost', () => {
    const results: CaseEvalResult[] = [
      {
        case_id: 'c1',
        success: true,
        latency_s: 1.0,
        input_tokens: 100,
        output_tokens: 200,
        cost_usd: 0.01
      },
      {
        case_id: 'c2',
        success: false,
        latency_s: 3.0,
        input_tokens: 150,
        output_tokens: 250,
        cost_usd: 0.02
      },
      {
        case_id: 'c3',
        success: true,
        latency_s: 2.0,
        input_tokens: 200,
        output_tokens: 300,
        cost_usd: 0.03
      },
      {
        case_id: 'c4',
        success: true,
        latency_s: 4.0,
        input_tokens: 100,
        output_tokens: 100,
        cost_usd: 0.005
      },
      {
        case_id: 'c5',
        success: false
      }
    ]
    const result = computeSummaryFromCases(results)
    expect(result.case_count).toBe(5)
    expect(result.success_rate).toBeCloseTo(0.6, 5) // 3/5
    expect(result.avg_latency_s).toBeCloseTo(2.5, 5) // (1+3+2+4)/4
    // tokens: case5 无 token 字段 = 0
    expect(result.total_tokens).toBe(100 + 200 + 150 + 250 + 200 + 300 + 100 + 100)
    expect(result.total_cost_usd).toBeCloseTo(0.01 + 0.02 + 0.03 + 0.005, 5)
  })
})
