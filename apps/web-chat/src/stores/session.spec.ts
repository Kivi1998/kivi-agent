// session store 单元测试（3 场景：load / add / select）
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useSessionStore } from './session'
import { createSessionApi, type FetchLike } from '@/api/session'
import type { SessionInfo } from '@/types/api'

const sample: SessionInfo = {
  session_id: 'sess-A',
  user_id: 'u-1',
  goal: 'g-A',
  created_at: '2026-07-23T00:00:00Z',
  status: 'active',
  run_id: null
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

describe('useSessionStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('load 覆盖本地 sessions 列表', async () => {
    const api = makeApi({
      '/api/sessions?user_id=u-1': {
        status: 200,
        body: { user_id: 'u-1', sessions: [sample, { ...sample, session_id: 'sess-B' }] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)
    await store.load('u-1')
    expect(store.sessions).toHaveLength(2)
    expect(store.hasSessions).toBe(true)
    expect(store.userId).toBe('u-1')
    expect(store.error).toBeNull()
  })

  it('add 创建 session 并选中', async () => {
    const newSession: SessionInfo = {
      ...sample,
      session_id: 'sess-NEW',
      goal: '新目标'
    }
    const api = makeApi({
      '/api/sessions': { status: 201, body: newSession }
    })
    const store = useSessionStore()
    store.setApi(api)
    const info = await store.add('新目标')
    expect(info.session_id).toBe('sess-NEW')
    expect(store.sessions[0]?.session_id).toBe('sess-NEW')
    expect(store.currentSessionId).toBe('sess-NEW')
    expect(store.currentSession?.goal).toBe('新目标')
  })

  it('select 切换 currentSessionId', async () => {
    const api = makeApi({
      '/api/sessions?user_id=u-1': {
        status: 200,
        body: { user_id: 'u-1', sessions: [sample, { ...sample, session_id: 'sess-B' }] }
      }
    })
    const store = useSessionStore()
    store.setApi(api)
    await store.load('u-1')
    store.select('sess-B')
    expect(store.currentSessionId).toBe('sess-B')
    expect(store.currentSession?.session_id).toBe('sess-B')
    store.select(null)
    expect(store.currentSessionId).toBeNull()
    expect(store.currentSession).toBeNull()
  })
})
