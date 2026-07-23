// team dashboard REST API 客户端
//
// 与后端 gateway/team_dashboard.py 5 个端点对齐（agent: package-dashboard-team-v52）
// 全部请求通过 fetch 发送，base URL 与 dashboard API 一致（/api）
//
// 类型字段命名与后端 Pydantic 模型保持 snake_case；
// 前端 UI 组件可按需映射到 camelCase（不在本层做转换，避免契约失真）

import type {
  DelegationStep,
  T11Metrics,
  TeamDetail,
  TeamListResponse,
  TeamSummary
} from '@/types/api'

/** 客户端可注入的 fetch 实现（默认用全局 fetch） */
export type TeamFetchLike = (
  input: string,
  init?: RequestInit
) => Promise<Response>

/** API 客户端配置（base URL + fetch 实现） */
export interface TeamDashboardApiOptions {
  baseUrl?: string
  fetchImpl?: TeamFetchLike
}

const DEFAULT_BASE_URL = '/api'

/** 创建 Team Dashboard API 客户端 */
export function createTeamDashboardApi(options: TeamDashboardApiOptions = {}) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL
  const fetchImpl: TeamFetchLike = options.fetchImpl ?? fetch.bind(globalThis)

  /** 解析 JSON 响应，非 2xx 抛出错误 */
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(
        `team dashboard api error: ${res.status} ${res.statusText} ${text}`
      )
    }
    return (await res.json()) as T
  }

  /** 全局 T11 6 指标汇总（team_count / success_rate / avg_delegation_accuracy / handoff_quality / coordination_latency / utilization） */
  function getTeamSummary(): Promise<TeamSummary> {
    return request<TeamSummary>('/team/summary', { method: 'GET' })
  }

  /** 列出最近 team 计划（分页：limit + offset） */
  function listTeams(
    limit: number,
    offset: number
  ): Promise<TeamListResponse> {
    const qs = new URLSearchParams({
      limit: String(limit),
      offset: String(offset)
    })
    return request<TeamListResponse>(`/team/teams?${qs.toString()}`, {
      method: 'GET'
    })
  }

  /** 单 team 详情（含每个 member 的 MemberOutcome） */
  function getTeam(teamId: string): Promise<TeamDetail> {
    return request<TeamDetail>(
      `/team/teams/${encodeURIComponent(teamId)}`,
      { method: 'GET' }
    )
  }

  /** 单 team 的委派步骤流（DelegationStep 列表） */
  function getTeamDelegations(teamId: string): Promise<DelegationStep[]> {
    return request<DelegationStep[]>(
      `/team/teams/${encodeURIComponent(teamId)}/delegations`,
      { method: 'GET' }
    )
  }

  /** 单 team 的 6 T11 指标 */
  function getTeamMetrics(teamId: string): Promise<T11Metrics> {
    return request<T11Metrics>(
      `/team/teams/${encodeURIComponent(teamId)}/metrics`,
      { method: 'GET' }
    )
  }

  return {
    getTeamSummary,
    listTeams,
    getTeam,
    getTeamDelegations,
    getTeamMetrics,
    request
  }
}

export type TeamDashboardApi = ReturnType<typeof createTeamDashboardApi>

/** 内部 helper：前端用 member outcomes 数组再算一次 T11 核心指标（供 TeamDashboard 视图 fallback 使用） */
export function computeTeamSummaryFromOutcomes(
  outcomes: Array<{ success: boolean; steps: number; tool_calls: number }>
): Pick<TeamSummary, 'team_count' | 'success_rate'> {
  const total = outcomes.length
  const success = outcomes.filter((o) => o.success).length
  return {
    team_count: total,
    success_rate: total > 0 ? success / total : 0
  }
}
