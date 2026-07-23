// TeamDashboard 总览视图测试（2 场景：空 / 有数据 + 行点击跳详情）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import TeamDashboard from './TeamDashboard.vue'
import type { TeamFetchLike } from '@/api/team_dashboard'
import type { TeamSummary, TeamSummaryItem } from '@/types/api'

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

const fakeSummary: TeamSummary = {
  team_count: 3,
  success_rate: 0.7,
  avg_delegation_accuracy: 0.85,
  avg_handoff_quality: 0.9,
  avg_coordination_latency_s: 5.5,
  avg_agent_utilization: 0.6
}

const fakeTeams: TeamSummaryItem[] = [
  {
    team_id: 'team-1',
    goal: '调研',
    member_count: 3,
    success: true,
    created_at: '2026-07-23T00:00:00Z',
    finished_at: '2026-07-23T00:01:00Z'
  }
]

describe('TeamDashboard view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('空数据：summary 全 0 + teams 显示 empty', async () => {
    const { fn } = makeFetch({
      '/api/team/summary': {
        status: 200,
        body: {
          team_count: 0,
          success_rate: 0,
          avg_delegation_accuracy: 0,
          avg_handoff_quality: 0,
          avg_coordination_latency_s: 0,
          avg_agent_utilization: 0
        }
      },
      '/api/team/teams?limit=20&offset=0': { status: 200, body: { total: 0, teams: [] } }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team')
      await router.isReady()
      const wrapper = mount(TeamDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="team-dashboard-overview"]').exists()).toBe(true)
      // 全 0 时 TeamSummaryCard 显示 0.0% / 0.00s
      expect(wrapper.find('[data-testid="team-summary-card"]').text()).toContain('0.0%')
      expect(wrapper.find('[data-testid="teams-empty"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('有数据：渲染 summary + teams + 点击行跳 team 详情', async () => {
    const { fn } = makeFetch({
      '/api/team/summary': { status: 200, body: fakeSummary },
      '/api/team/teams?limit=20&offset=0': {
        status: 200,
        body: { total: 1, teams: fakeTeams }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(TeamDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="tmetric-success-rate"]').text()).toContain(
        '70.0%'
      )
      expect(wrapper.findAll('[data-testid^="teams-row-"]')).toHaveLength(1)
      await wrapper.find('[data-testid="teams-row-team-1"]').trigger('click')
      expect(pushSpy).toHaveBeenCalled()
      const last = pushSpy.mock.calls[pushSpy.mock.calls.length - 1]?.[0]
      expect(last).toMatchObject({
        name: 'team-dashboard-detail',
        params: { teamId: 'team-1' }
      })
    } finally {
      global.fetch = orig
    }
  })
})
