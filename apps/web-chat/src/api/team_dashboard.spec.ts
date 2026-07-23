// team dashboard API 单元测试（9 场景：5 端点 + computeTeamSummaryFromOutcomes + 错误处理 + 边界）
import { describe, it, expect, vi } from 'vitest'
import {
  createTeamDashboardApi,
  computeTeamSummaryFromOutcomes,
  type TeamFetchLike
} from './team_dashboard'
import type {
  DelegationStep,
  T11Metrics,
  TeamDetail,
  TeamListResponse,
  TeamSummary,
  TeamSummaryItem
} from '@/types/api'

/** 测试用 fetch mock：根据 URL 分发响应 */
function makeFetchMock(
  responses: Record<string, { status: number; body: unknown }>
): {
  fn: TeamFetchLike
  calls: Array<{ url: string; init?: RequestInit }>
} {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn: TeamFetchLike = async (input, init) => {
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

const fakeSummary: TeamSummary = {
  team_count: 5,
  success_rate: 0.8,
  avg_delegation_accuracy: 0.9,
  avg_handoff_quality: 0.85,
  avg_coordination_latency_s: 12.5,
  avg_agent_utilization: 0.7
}

const fakeTeamItem: TeamSummaryItem = {
  team_id: 'team-1',
  goal: '调研并对比 X 和 Y 框架',
  member_count: 3,
  success: true,
  created_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:01:00Z'
}

const fakeTeamList: TeamListResponse = {
  total: 2,
  teams: [
    fakeTeamItem,
    {
      team_id: 'team-2',
      goal: '写一份报告',
      member_count: 2,
      success: false,
      created_at: '2026-07-22T00:00:00Z',
      finished_at: null
    }
  ]
}

const fakeTeamDetail: TeamDetail = {
  team_id: 'team-1',
  goal: '调研并对比 X 和 Y 框架',
  member_count: 2,
  success: true,
  created_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:01:00Z',
  member_outcomes: [
    {
      member_id: 'researcher',
      role: 'research',
      success: true,
      steps: 5,
      tool_calls: 3,
      finished_at: '2026-07-23T00:00:30Z',
      final_answer: '找到 3 篇相关资料'
    },
    {
      member_id: 'writer',
      role: 'writer',
      success: true,
      steps: 4,
      tool_calls: 1,
      finished_at: '2026-07-23T00:01:00Z',
      final_answer: '已生成报告'
    }
  ]
}

const fakeDelegations: DelegationStep[] = [
  {
    step_id: 'd-1',
    from_member: 'lead',
    to_member: 'researcher',
    sub_task: '收集 X 框架资料',
    message: '请帮忙查 X',
    success: true,
    ts: '2026-07-23T00:00:05Z'
  },
  {
    step_id: 'd-2',
    from_member: 'researcher',
    to_member: 'writer',
    sub_task: '汇总报告',
    message: '资料已收集',
    success: true,
    ts: '2026-07-23T00:00:30Z'
  }
]

const fakeT11Metrics: T11Metrics = {
  team_success_rate: { rate: 1.0, passed: 1, total: 1 },
  delegation_accuracy: { rate: 0.8, matched: 4, applicable: 5 },
  handoff_quality: { rate: 1.0, successful: 2, total: 2 },
  coordination_latency_s: { avg_s: 60.0, p50_s: 60.0, p95_s: 60.0, count: 1 },
  agent_utilization: { rate: 0.6, tool_calls: 4, total_steps: 10 },
  role_consistency: { rate: 1.0, role_changes: 0, total_steps: 10 }
}

describe('createTeamDashboardApi', () => {
  it('getTeamSummary GET /team/summary returns summary', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/team/summary': { status: 200, body: fakeSummary }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const result = await api.getTeamSummary()
    expect(result).toEqual(fakeSummary)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('/api/team/summary')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('listTeams GET /team/teams?limit=&offset= unwraps teams[]', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/team/teams?limit=20&offset=0': {
        status: 200,
        body: fakeTeamList
      }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const result = await api.listTeams(20, 0)
    expect(result.total).toBe(2)
    expect(result.teams).toHaveLength(2)
    expect(result.teams[0]?.team_id).toBe('team-1')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getTeam GET /team/teams/:teamId returns detail with member_outcomes', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/team/teams/team-1': { status: 200, body: fakeTeamDetail }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const detail = await api.getTeam('team-1')
    expect(detail.team_id).toBe('team-1')
    expect(detail.member_outcomes).toHaveLength(2)
    expect(detail.member_outcomes[0]?.role).toBe('research')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getTeam encodes special characters in teamId', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/team/teams/team%2Fwith%2Fslash': {
        status: 200,
        body: { ...fakeTeamDetail, team_id: 'team/with/slash' }
      }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    await api.getTeam('team/with/slash')
    expect(calls[0]?.url).toBe('/api/team/teams/team%2Fwith%2Fslash')
  })

  it('getTeamDelegations GET /team/teams/:teamId/delegations returns step list', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/team/teams/team-1/delegations': {
        status: 200,
        body: fakeDelegations
      }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const ds = await api.getTeamDelegations('team-1')
    expect(ds).toHaveLength(2)
    expect(ds[0]?.from_member).toBe('lead')
    expect(ds[0]?.to_member).toBe('researcher')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getTeamMetrics GET /team/teams/:teamId/metrics returns T11Metrics', async () => {
    const { fn } = makeFetchMock({
      '/api/team/teams/team-1/metrics': { status: 200, body: fakeT11Metrics }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const m = await api.getTeamMetrics('team-1')
    expect(m.team_success_rate.rate).toBe(1.0)
    expect(m.delegation_accuracy.matched).toBe(4)
    expect(m.handoff_quality.successful).toBe(2)
  })

  it('非 2xx 响应抛错且消息含状态码', async () => {
    const fn: TeamFetchLike = vi.fn(async () =>
      new Response('boom', { status: 503, statusText: 'Service Unavailable' })
    ) as unknown as TeamFetchLike
    const api = createTeamDashboardApi({ fetchImpl: fn })
    await expect(api.getTeamSummary()).rejects.toThrow(/503/)
  })

  it('暴露内部 request helper（advanced 用）', async () => {
    const { fn } = makeFetchMock({
      '/api/team/custom-path': { status: 200, body: { ok: true } }
    })
    const api = createTeamDashboardApi({ fetchImpl: fn })
    const r = await api.request<{ ok: boolean }>('/team/custom-path')
    expect(r.ok).toBe(true)
  })
})

describe('computeTeamSummaryFromOutcomes', () => {
  it('空数组：team_count=0 + success_rate=0', () => {
    const r = computeTeamSummaryFromOutcomes([])
    expect(r.team_count).toBe(0)
    expect(r.success_rate).toBe(0)
  })

  it('3 个 outcome：2 成功 → success_rate=2/3', () => {
    const r = computeTeamSummaryFromOutcomes([
      { success: true, steps: 3, tool_calls: 2 },
      { success: true, steps: 5, tool_calls: 4 },
      { success: false, steps: 2, tool_calls: 1 }
    ])
    expect(r.team_count).toBe(3)
    expect(r.success_rate).toBeCloseTo(2 / 3, 5)
  })
})
