// coding dashboard REST API 客户端
//
// 与后端 gateway/coding_dashboard.py 5 个端点对齐（agent: package-dashboard-coding-v52）
// 全部请求通过 fetch 发送，base URL 与 dashboard API 一致（/api）
//
// 类型字段命名与后端 Pydantic 模型保持 snake_case；
// 前端 UI 组件可按需映射到 camelCase（不在本层做转换，避免契约失真）

import type {
  CodingDetail,
  CodingRunListResponse,
  CodingSummary,
  PatchRecord,
  T12Metrics
} from '@/types/api'

/** 客户端可注入的 fetch 实现（默认用全局 fetch） */
export type CodingFetchLike = (
  input: string,
  init?: RequestInit
) => Promise<Response>

/** API 客户端配置（base URL + fetch 实现） */
export interface CodingDashboardApiOptions {
  baseUrl?: string
  fetchImpl?: CodingFetchLike
}

const DEFAULT_BASE_URL = '/api'

/** 创建 Coding Dashboard API 客户端 */
export function createCodingDashboardApi(
  options: CodingDashboardApiOptions = {}
) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL
  const fetchImpl: CodingFetchLike =
    options.fetchImpl ?? fetch.bind(globalThis)

  /** 解析 JSON 响应，非 2xx 抛出错误 */
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(
        `coding dashboard api error: ${res.status} ${res.statusText} ${text}`
      )
    }
    return (await res.json()) as T
  }

  /** 全局 T12 8 指标汇总（run_count / task_completion / tests_passed / iteration / time_to_first_pass / self_recovery） */
  function getCodingSummary(): Promise<CodingSummary> {
    return request<CodingSummary>('/coding/summary', { method: 'GET' })
  }

  /** 列出最近 coding run（分页：limit + offset） */
  function listCodingRuns(
    limit: number,
    offset: number
  ): Promise<CodingRunListResponse> {
    const qs = new URLSearchParams({
      limit: String(limit),
      offset: String(offset)
    })
    return request<CodingRunListResponse>(
      `/coding/runs?${qs.toString()}`,
      { method: 'GET' }
    )
  }

  /** 单 coding run 详情（含 patches + test_runs） */
  function getCodingRun(runId: string): Promise<CodingDetail> {
    return request<CodingDetail>(
      `/coding/runs/${encodeURIComponent(runId)}`,
      { method: 'GET' }
    )
  }

  /** 单 coding run 的 patch 列表（unified diff） */
  function getCodingPatches(runId: string): Promise<PatchRecord[]> {
    return request<PatchRecord[]>(
      `/coding/runs/${encodeURIComponent(runId)}/patches`,
      { method: 'GET' }
    )
  }

  /** 单 coding run 的 8 T12 指标 */
  function getCodingMetrics(runId: string): Promise<T12Metrics> {
    return request<T12Metrics>(
      `/coding/runs/${encodeURIComponent(runId)}/metrics`,
      { method: 'GET' }
    )
  }

  return {
    getCodingSummary,
    listCodingRuns,
    getCodingRun,
    getCodingPatches,
    getCodingMetrics,
    request
  }
}

export type CodingDashboardApi = ReturnType<typeof createCodingDashboardApi>

/** 内部 helper：前端用 coding run 列表算一次核心指标（供 CodingDashboard 视图 fallback 使用） */
export function computeCodingSummaryFromRuns(
  runs: Array<{ success: boolean; iteration_count: number }>
): Pick<CodingSummary, 'run_count' | 'task_completion_rate' | 'avg_iteration_count'> {
  const total = runs.length
  const success = runs.filter((r) => r.success).length
  const iterations = runs.reduce((acc, r) => acc + r.iteration_count, 0)
  return {
    run_count: total,
    task_completion_rate: total > 0 ? success / total : 0,
    avg_iteration_count: total > 0 ? iterations / total : 0
  }
}
