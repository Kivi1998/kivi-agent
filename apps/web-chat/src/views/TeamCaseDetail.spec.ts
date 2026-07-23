// TeamCaseDetail 视图测试（3 场景：找到 / 找不到 / 返回 team）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import TeamCaseDetail from './TeamCaseDetail.vue'
import type { TeamFetchLike } from '@/api/team_dashboard'
import type { TeamDetail } from '@/types/api'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
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

function makeFetch(responses: Record<string, { status: number; body: unknown }>): {
  fn: TeamFetchLike
} {
  const fn: TeamFetchLike = async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return { fn }
}

const fakeDetail: TeamDetail = {
  team_id: 'team-1',
  goal: '调研',
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
      final_answer: '找到 3 篇资料'
    },
    {
      member_id: 'writer',
      role: 'writer',
      success: false,
      steps: 2,
      tool_calls: 0,
      finished_at: null,
      final_answer: ''
    }
  ]
}

describe('TeamCaseDetail view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('找到成员：渲染 summary 6 tile + final_answer', async () => {
    const { fn } = makeFetch({
      '/api/team/teams/team-1': { status: 200, body: fakeDetail }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team/team-1/cases/researcher')
      await router.isReady()
      const wrapper = mount(TeamCaseDetail, {
        props: { teamId: 'team-1', caseId: 'researcher' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="team-case-detail"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="team-case-not-found"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="team-case-member-id"]').text()).toContain('researcher')
      expect(wrapper.find('[data-testid="team-case-role"]').text()).toContain('research')
      expect(wrapper.find('[data-testid="team-case-success"]').text()).toContain('✓')
      expect(wrapper.find('[data-testid="team-case-steps"]').text()).toContain('5')
      expect(wrapper.find('[data-testid="team-case-tool-calls"]').text()).toContain('3')
      expect(wrapper.find('[data-testid="team-case-final-pre"]').text()).toContain(
        '找到 3 篇资料'
      )
    } finally {
      global.fetch = orig
    }
  })

  it('找不到成员：显示 "找不到该成员" empty', async () => {
    const { fn } = makeFetch({
      '/api/team/teams/team-1': { status: 200, body: fakeDetail }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team/team-1/cases/missing')
      await router.isReady()
      const wrapper = mount(TeamCaseDetail, {
        props: { teamId: 'team-1', caseId: 'missing' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="team-case-not-found"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="team-case-not-found"]').text()).toContain('missing')
    } finally {
      global.fetch = orig
    }
  })

  it('返回按钮：跳 team detail', async () => {
    const { fn } = makeFetch({
      '/api/team/teams/team-1': { status: 200, body: fakeDetail }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/team/team-1/cases/researcher')
      await router.isReady()
      const pushSpy = vi.spyOn(router, 'push')
      const wrapper = mount(TeamCaseDetail, {
        props: { teamId: 'team-1', caseId: 'researcher' },
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      await wrapper.find('[data-testid="team-case-back-btn"]').trigger('click')
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
