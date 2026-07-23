// dashboard REST API 客户端
//
// 与后端 gateway/dashboard.py 5 个端点对齐（agent: package-dashboard-frontend-v51）
// 全部请求通过 fetch 发送，base URL 与 session API 一致（/api）
//
// 类型字段命名与后端 Pydantic 模型保持 snake_case；
// 前端 UI 组件可按需映射到 camelCase（不在本层做转换，避免契约失真）

import type {
  CaseEvalResult,
  RunSummary,
  RunDetail,
  Summary,
  TracesResponse,
  MetricsReport
} from '@/types/api'

/** 客户端可注入的 fetch 实现（默认用全局 fetch） */
export type FetchLike = (
  input: string,
  init?: RequestInit
) => Promise<Response>

/** API 客户端配置（base URL + fetch 实现） */
export interface DashboardApiOptions {
  baseUrl?: string
  fetchImpl?: FetchLike
}

const DEFAULT_BASE_URL = '/api'

/** 创建 Dashboard API 客户端 */
export function createDashboardApi(options: DashboardApiOptions = {}) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL
  const fetchImpl: FetchLike = options.fetchImpl ?? fetch.bind(globalThis)

  /** 解析 JSON 响应，非 2xx 抛出错误 */
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(
        `dashboard api error: ${res.status} ${res.statusText} ${text}`
      )
    }
    return (await res.json()) as T
  }

  /** 获取全局汇总（case_count / success_rate / avg_latency_s / total_tokens / total_cost_usd） */
  function fetchSummary(): Promise<Summary> {
    return request<Summary>('/dashboard/summary', { method: 'GET' })
  }

  /** 列出最近评测运行（分页：limit + offset） */
  function fetchRuns(
    limit: number,
    offset: number
  ): Promise<{ total: number; runs: RunSummary[] }> {
    const qs = new URLSearchParams({
      limit: String(limit),
      offset: String(offset)
    })
    return request<{ total: number; runs: RunSummary[] }>(
      `/dashboard/runs?${qs.toString()}`,
      { method: 'GET' }
    )
  }

  /** 单 run 详情（含每 case 的 EvalResult） */
  function fetchRunDetail(runId: string): Promise<RunDetail> {
    return request<RunDetail>(
      `/dashboard/runs/${encodeURIComponent(runId)}`,
      { method: 'GET' }
    )
  }

  /** 单 run 的 7 指标汇总（与 metrics_report 一致） */
  function fetchMetrics(runId: string): Promise<MetricsReport> {
    return request<MetricsReport>(
      `/dashboard/runs/${encodeURIComponent(runId)}/metrics`,
      { method: 'GET' }
    )
  }

  /** 单 run 的事件流；可选 case_id 过滤 */
  function fetchTraces(
    runId: string,
    caseId?: string
  ): Promise<TracesResponse> {
    const qs = caseId
      ? new URLSearchParams({ case_id: caseId }).toString()
      : ''
    const path = `/dashboard/runs/${encodeURIComponent(runId)}/traces${qs ? `?${qs}` : ''}`
    return request<TracesResponse>(path, { method: 'GET' })
  }

  return {
    fetchSummary,
    fetchRuns,
    fetchRunDetail,
    fetchMetrics,
    fetchTraces,
    request
  }
}

export type DashboardApi = ReturnType<typeof createDashboardApi>

/** 内部 helper：前端用 case results 数组再算一次 7 指标（供 Dashboard 视图 fallback 使用） */
export function computeSummaryFromCases(
  results: CaseEvalResult[]
): Summary {
  const total = results.length
  const success = results.filter((r) => r.success).length
  const latencies = results
    .map((r) => r.latency_s)
    .filter((n): n is number => typeof n === 'number')
  const avgLatency =
    latencies.length > 0
      ? latencies.reduce((acc, n) => acc + n, 0) / latencies.length
      : 0
  const totalTokens = results.reduce(
    (acc, r) => acc + (r.input_tokens ?? 0) + (r.output_tokens ?? 0),
    0
  )
  const totalCost = results.reduce((acc, r) => acc + (r.cost_usd ?? 0), 0)
  return {
    case_count: total,
    success_rate: total > 0 ? success / total : 0,
    avg_latency_s: avgLatency,
    total_tokens: totalTokens,
    total_cost_usd: totalCost
  }
}
