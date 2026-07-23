// ChatView 视图测试（2 场景：空消息 / 1 消息）
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ChatView from './ChatView.vue'
import { createSessionApi, type FetchLike } from '@/api/session'
import { useSessionStore } from '@/stores/session'
import { useMessageStore, type ChatMessage } from '@/stores/message'
import type { SessionInfo } from '@/types/api'

const sampleSession: SessionInfo = {
  session_id: 'sess-chat',
  user_id: 'u-1',
  goal: 'test chat',
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

describe('ChatView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('空消息：显示 empty messages 提示', async () => {
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions: [sampleSession] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)
    store.select(sampleSession.session_id)

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(ChatView, {
      props: { sessionId: 'sess-chat' },
      global: { plugins: [router] }
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="chat-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="empty-messages"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="message-list"]').exists()).toBe(false)
  })

  it('1 消息：渲染消息卡片 + 发送后追加', async () => {
    const api = makeApi({
      '/api/sessions?user_id=default-user': {
        status: 200,
        body: { user_id: 'default-user', sessions: [sampleSession] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)
    store.select(sampleSession.session_id)

    const messageStore = useMessageStore()
    const msg: ChatMessage = {
      id: 'msg-1',
      session_id: 'sess-chat',
      role: 'user',
      content: 'hello',
      created_at: '2026-07-23T00:00:00Z'
    }
    messageStore.append(msg)

    const router = makeRouter()
    router.push('/')
    await router.isReady()

    const wrapper = mount(ChatView, {
      props: { sessionId: 'sess-chat' },
      global: { plugins: [router] }
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="empty-messages"]').exists()).toBe(false)
    const items = wrapper.findAll('[data-testid^="message-msg-"]')
    expect(items).toHaveLength(1)
    expect(items[0]?.text()).toContain('hello')

    // 触发 send 事件，验证消息会追加
    const input = wrapper.findComponent({ name: 'MessageInput' })
    input.vm.$emit('send', 'second message')
    await flushPromises()
    const after = wrapper.findAll('[data-testid^="message-"]')
    expect(after.length).toBeGreaterThanOrEqual(2)
  })
})
