// session API 单元测试（4 场景）
import { describe, it, expect, vi } from 'vitest'
import { createSessionApi, type FetchLike } from './session'
import type { SessionInfo, SessionListResponse } from '@/types/api'

/** 测试用 fetch mock：根据 URL 分发响应 */
function makeFetchMock(responses: Record<string, { status: number; body: unknown }>): {
  fn: FetchLike
  calls: Array<{ url: string; init?: RequestInit }>
} {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn: FetchLike = async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url
    calls.push({ url, init })
    const r = responses[url]
    if (!r) {
      return new Response(JSON.stringify({ error: 'not found' }), { status: 404 })
    }
    return new Response(JSON.stringify(r.body), { status: r.status })
  }
  return { fn, calls }
}

const fakeSession: SessionInfo = {
  session_id: 'sess-1',
  user_id: 'u-1',
  goal: 'test goal',
  created_at: '2026-07-23T00:00:00Z',
  status: 'active',
  run_id: 'run-1'
}

describe('createSessionApi', () => {
  it('startSession POST /sessions and returns info', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/sessions': { status: 201, body: fakeSession }
    })
    const api = createSessionApi({ fetchImpl: fn })
    const info = await api.startSession({ user_id: 'u-1', goal: 'test goal' })
    expect(info).toEqual(fakeSession)
    expect(calls).toHaveLength(1)
    expect(calls[0]?.url).toBe('/api/sessions')
    expect(calls[0]?.init?.method).toBe('POST')
  })

  it('getSession GET /sessions/{id} and returns info', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/sessions/sess-1': { status: 200, body: fakeSession }
    })
    const api = createSessionApi({ fetchImpl: fn })
    const info = await api.getSession('sess-1')
    expect(info).toEqual(fakeSession)
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('listSessions GET /sessions?user_id=... and unwraps sessions[]', async () => {
    const listResp: SessionListResponse = {
      user_id: 'u-1',
      sessions: [fakeSession, { ...fakeSession, session_id: 'sess-2' }]
    }
    const { fn } = makeFetchMock({
      '/api/sessions?user_id=u-1': { status: 200, body: listResp }
    })
    const api = createSessionApi({ fetchImpl: fn })
    const list = await api.listSessions('u-1')
    expect(list).toHaveLength(2)
    expect(list[0]?.session_id).toBe('sess-1')
    expect(list[1]?.session_id).toBe('sess-2')
  })

  it('cancelSession POST /sessions/{id}/cancel and returns cancel response', async () => {
    const cancelResp = { cancelled: true, session_id: 'sess-1', ts: '2026-07-23T00:01:00Z' }
    const { fn, calls } = makeFetchMock({
      '/api/sessions/sess-1/cancel': { status: 200, body: cancelResp }
    })
    const api = createSessionApi({ fetchImpl: fn })
    const result = await api.cancelSession('sess-1', 'user_requested')
    expect(result.cancelled).toBe(true)
    expect(calls[0]?.init?.method).toBe('POST')
    const body = JSON.parse((calls[0]?.init?.body as string) ?? '{}')
    expect(body.reason).toBe('user_requested')
  })
})

describe('error handling', () => {
  it('throws on non-2xx response with status code in message', async () => {
    const fn: FetchLike = vi.fn(async () =>
      new Response('boom', { status: 500, statusText: 'Internal Server Error' })
    ) as unknown as FetchLike
    const api = createSessionApi({ fetchImpl: fn })
    await expect(api.getSession('x')).rejects.toThrow(/500/)
  })
})
