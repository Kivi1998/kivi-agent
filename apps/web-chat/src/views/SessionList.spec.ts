// SessionList 视图测试（3 场景：空列表 / 1 session / 多 session）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import SessionList from './SessionList.vue'
import { createSessionApi, type FetchLike } from '@/api/session'
import { useSessionStore } from '@/stores/session'
import type { SessionInfo } from '@/types/api'

const baseSession: SessionInfo = {
  session_id: 'sess-1',
  user_id: 'u-1',
  goal: 'goal 1',
  created_at: '2026-07-23T00:00:00Z',
  status: 'active',
  run_id: null
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'session-list', component: { template: '<div/>' } },
      { path: '/chat/:sessionId', name: 'chat', component: { template: '<div/>' } }
    ]
  })
}

function makeApi(responses: Record<string, { status: number; body: unknown }>) {
  const fetchImpl: FetchLike = async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return createSessionApi({ fetchImpl })
}

describe('SessionList view', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('空列表：显示 empty state', async () => {
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions: [] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(SessionList, {
      global: { plugins: [router] }
    })
    await flushPromises()
    await flushPromises()

    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="session-list"]').exists()).toBe(false)
  })

  it('1 session：显示单个 session 卡片', async () => {
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions: [baseSession] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(SessionList, {
      global: { plugins: [router] }
    })
    await flushPromises()
    await flushPromises()

    const items = wrapper.findAll('[data-testid^="session-item-"]')
    expect(items).toHaveLength(1)
    expect(wrapper.find('[data-testid="empty-state"]').exists()).toBe(false)
  })

  it('多 session：渲染多个卡片 + 状态徽标', async () => {
    const sessions: SessionInfo[] = [
      { ...baseSession, session_id: 'sess-1', status: 'active' },
      { ...baseSession, session_id: 'sess-2', status: 'waiting_for_input' },
      { ...baseSession, session_id: 'sess-3', status: 'closed' }
    ]
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions }
      }
    })
    const store = useSessionStore()
    store.setApi(api)

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(SessionList, {
      global: { plugins: [router] }
    })
    await flushPromises()
    await flushPromises()

    const items = wrapper.findAll('[data-testid^="session-item-"]')
    expect(items).toHaveLength(3)
    expect(wrapper.find('[data-testid="session-status-sess-1"]').text()).toBe('active')
    expect(wrapper.find('[data-testid="session-status-sess-2"]').text()).toBe(
      'waiting_for_input'
    )
    expect(wrapper.find('[data-testid="session-status-sess-3"]').text()).toBe('closed')
  })

  it('点击 session 触发 select 事件', async () => {
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions: [baseSession] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)
    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const pushSpy = vi.spyOn(router, 'push')

    const wrapper = mount(SessionList, {
      global: { plugins: [router] }
    })
    await flushPromises()
    await flushPromises()

    const item = wrapper.find('[data-testid^="session-item-"]')
    await item.trigger('click')
    expect(pushSpy).toHaveBeenCalled()
    expect(pushSpy.mock.calls[0]?.[0]).toMatchObject({
      name: 'chat',
      params: { sessionId: 'sess-1' }
    })
  })
})
