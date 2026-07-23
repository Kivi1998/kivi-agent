// TeamDashboardDetail 视图测试（2 场景：有数据 + 失败 / 返回跳总览）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import TeamDashboardDetail from './TeamDashboardDetail.vue'
import type { TeamFetchLike } from '@/api/team_dashboard'
import type {
  DelegationStep,
  T11Metrics,
  TeamDetail
} from '@/types/api'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/dashboard/team',
        name: 'team-dashboard',
        component: { template: '<div/>' }
      },
      {
        path: '/dashboard/team/:teamId',
        name: 'team-dashboard-detail',
        component: { template: '<div/>' }
      },
      {
        path: '/dashboard/team/:teamId/cases/:caseId',
        name: 'team-case-detail',
        component: { template: '<div/>' }
      }
    ]
  })
}

function makeFetch(
  responses: Record<string, { status: number; body: unknown }>
): { fn: TeamFetchLike; urls: string[] } {
  const urls: string[] = []
  const fn: TeamFetchLike = async (input) => {
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

const fakeDetail: TeamDetail = {
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
      final_answer: 'ok'
    }
  ]
}

const fakeDelegations: DelegationStep[] = [
  {
    step_id: 'd-1',
    from_member: 'lead',
    to_member: 'researcher',
    sub_task: '查资料',
    message: 'help',
    success: true,
    ts: '2026-07-23T00:00:05Z'
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

describe('TeamDashboardDetail view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('有数据：渲染 summary + delegations + metrics + role timeline + member outcomes', async () => {
    const { fn, urls } = makeFetch({
      '/api/team/teams/team-1': { status: 200, body: fakeDetail },
      '/api/team/teams/team-1/delegations': { status: 200, body: fakeDelegations },
      '/api/team/teams/team-1/metrics': { status: 200, body: fakeT11Metrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team/team-1')
      await router.isReady()
      const wrapper = mount(TeamDashboardDetail, {
        props: { teamId: 'team-1' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="team-detail"]').exists()).toBe(true)
      // 3 个 endpoint 被调用
      expect(urls).toContain('/api/team/teams/team-1')
      expect(urls).toContain('/api/team/teams/team-1/delegations')
      expect(urls).toContain('/api/team/teams/team-1/metrics')
      // goal 截断 + member_count + success
      expect(wrapper.find('[data-testid="team-detail-goal"]').text()).toContain('调研')
      expect(wrapper.find('[data-testid="team-detail-member-count"]').text()).toContain('2')
      expect(wrapper.find('[data-testid="team-detail-success"]').text()).toContain('✓')
      // delegation tree
      expect(wrapper.find('[data-testid="delegation-svg"]').exists()).toBe(true)
      // role timeline
      expect(wrapper.find('[data-testid="role-timeline-table"]').exists()).toBe(true)
      // member outcomes
      expect(wrapper.find('[data-testid="member-outcomes-grid"]').exists()).toBe(true)
      // metrics 显示
      expect(wrapper.find('[data-testid="team-detail-metrics"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('返回按钮：点击触发 router.push({name: team-dashboard})', async () => {
    const { fn } = makeFetch({
      '/api/team/teams/team-1': { status: 200, body: fakeDetail },
      '/api/team/teams/team-1/delegations': { status: 200, body: [] },
      '/api/team/teams/team-1/metrics': { status: 200, body: fakeT11Metrics }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team/team-1')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(TeamDashboardDetail, {
        props: { teamId: 'team-1' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      await wrapper.find('[data-testid="team-back-btn"]').trigger('click')
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({ name: 'team-dashboard' })
    } finally {
      global.fetch = orig
    }
  })
})
