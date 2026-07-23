// memory dashboard API 单元测试（11 场景：8 端点 + 错误处理 + URL 编码 + helpers）
import { describe, it, expect, vi } from 'vitest'
import {
  createMemoryDashboardApi,
  formatImportance,
  MEMORY_STATUS_LABELS,
  MEMORY_TYPE_LABELS,
  computeMemorySummary,
  type MemoryFetchLike
} from './memory'
import type {
  MemoryAuditResponse,
  MemoryItem,
  MemoryItemResponse,
  MemoryListResponse,
  MemorySearchResponse
} from '@/types/api'

/** 测试用 fetch mock：根据 URL 分发响应 */
function makeFetchMock(
  responses: Record<string, { status: number; body: unknown }>
): {
  fn: MemoryFetchLike
  calls: Array<{ url: string; init?: RequestInit }>
} {
  const calls: Array<{ url: string; init?: RequestInit }> = []
  const fn: MemoryFetchLike = async (input, init) => {
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

const fakeItem: MemoryItem = {
  id: 'mem-1',
  content: '用户偏好中文回复',
  memory_type: 'user',
  importance: 0.85,
  status: 'active',
  source: 'session-abc',
  created_at: '2026-07-23T00:00:00Z',
  expires_at: null,
  updated_at: '2026-07-23T00:01:00Z'
}

const fakeList: MemoryListResponse = {
  total: 2,
  items: [
    fakeItem,
    {
      id: 'mem-2',
      content: '用户反馈喜欢简洁报告',
      memory_type: 'feedback',
      importance: 0.6,
      status: 'pending',
      source: 'session-xyz',
      created_at: '2026-07-22T00:00:00Z',
      expires_at: null,
      updated_at: null
    }
  ]
}

const fakeItemResponse: MemoryItemResponse = { item: fakeItem }

const fakeSearch: MemorySearchResponse = {
  query: '用户偏好',
  top_k: 3,
  results: [
    {
      id: 'mem-1',
      content: '用户偏好中文回复',
      score: 0.92,
      memory_type: 'user',
      importance: 0.85,
      status: 'active',
      source: 'session-abc',
      created_at: '2026-07-23T00:00:00Z'
    },
    {
      id: 'mem-2',
      content: '用户反馈喜欢简洁报告',
      score: 0.7,
      memory_type: 'feedback',
      importance: 0.6,
      status: 'pending',
      source: 'session-xyz',
      created_at: '2026-07-22T00:00:00Z'
    }
  ]
}

const fakeAudit: MemoryAuditResponse = {
  memory_id: 'mem-1',
  events: [
    {
      event_id: 'evt-1',
      memory_id: 'mem-1',
      action: 'create',
      actor: 'system',
      ts: '2026-07-23T00:00:00Z',
      detail: {}
    },
    {
      event_id: 'evt-2',
      memory_id: 'mem-1',
      action: 'update',
      actor: 'admin',
      ts: '2026-07-23T00:01:00Z',
      detail: { field: 'importance', from: 0.5, to: 0.85 }
    }
  ]
}

describe('createMemoryDashboardApi', () => {
  it('listMemoryItems GET /memory/items 默认无过滤', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items': { status: 200, body: fakeList }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.listMemoryItems()
    expect(r.total).toBe(2)
    expect(r.items).toHaveLength(2)
    expect(calls[0]?.url).toBe('/api/memory/items')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('listMemoryItems 带过滤参数（status / memory_type / source / limit / offset）', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items?status=active&memory_type=user&source=session-abc&limit=10&offset=20':
        { status: 200, body: { total: 1, items: [fakeItem] } }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.listMemoryItems({
      status: 'active',
      memory_type: 'user',
      source: 'session-abc',
      limit: 10,
      offset: 20
    })
    expect(r.total).toBe(1)
    expect(calls[0]?.url).toBe(
      '/api/memory/items?status=active&memory_type=user&source=session-abc&limit=10&offset=20'
    )
  })

  it('getMemoryItem GET /memory/items/:id unwraps item', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items/mem-1': { status: 200, body: fakeItemResponse }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.getMemoryItem('mem-1')
    expect(r.item.id).toBe('mem-1')
    expect(r.item.content).toBe('用户偏好中文回复')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getMemoryItem 对 id 中含 / 的情况做 URL 编码', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items/mem%2Fwith%2Fslash': {
        status: 200,
        body: { item: { ...fakeItem, id: 'mem/with/slash' } }
      }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    await api.getMemoryItem('mem/with/slash')
    expect(calls[0]?.url).toBe('/api/memory/items/mem%2Fwith%2Fslash')
  })

  it('createMemoryItem POST /memory/items 发送 JSON body', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items': { status: 201, body: fakeItemResponse }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.createMemoryItem({
      content: '新记忆',
      memory_type: 'task',
      importance: 0.5
    })
    expect(r.item.id).toBe('mem-1')
    expect(calls[0]?.init?.method).toBe('POST')
    const body = JSON.parse(calls[0]?.init?.body as string)
    expect(body).toEqual({
      content: '新记忆',
      memory_type: 'task',
      importance: 0.5
    })
  })

  it('updateMemoryItem PATCH /memory/items/:id 发送 JSON body', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items/mem-1': { status: 200, body: fakeItemResponse }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    await api.updateMemoryItem('mem-1', { importance: 0.95, status: 'archived' })
    expect(calls[0]?.init?.method).toBe('PATCH')
    const body = JSON.parse(calls[0]?.init?.body as string)
    expect(body).toEqual({ importance: 0.95, status: 'archived' })
  })

  it('deleteMemoryItem DELETE /memory/items/:id 返回 deleted 标志', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items/mem-1': { status: 200, body: { deleted: true } }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.deleteMemoryItem('mem-1')
    expect(r.deleted).toBe(true)
    expect(calls[0]?.init?.method).toBe('DELETE')
  })

  it('archiveMemoryItem POST /memory/items/:id/archive', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/items/mem-1/archive': {
        status: 200,
        body: { item: { ...fakeItem, status: 'archived' } }
      }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.archiveMemoryItem('mem-1')
    expect(r.item.status).toBe('archived')
    expect(calls[0]?.init?.method).toBe('POST')
    expect(calls[0]?.url).toBe('/api/memory/items/mem-1/archive')
  })

  it('searchMemory GET /memory/search?q=&top_k=', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/search?q=%E7%94%A8%E6%88%B7%E5%81%8F%E5%A5%BD&top_k=3': {
        status: 200,
        body: fakeSearch
      }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.searchMemory('用户偏好', 3)
    expect(r.query).toBe('用户偏好')
    expect(r.top_k).toBe(3)
    expect(r.results).toHaveLength(2)
    expect(r.results[0]?.score).toBeCloseTo(0.92, 5)
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('getMemoryAudit GET /memory/audit?memory_id=', async () => {
    const { fn, calls } = makeFetchMock({
      '/api/memory/audit?memory_id=mem-1': { status: 200, body: fakeAudit }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.getMemoryAudit('mem-1')
    expect(r.memory_id).toBe('mem-1')
    expect(r.events).toHaveLength(2)
    expect(r.events[0]?.action).toBe('create')
    expect(r.events[1]?.action).toBe('update')
    expect(calls[0]?.init?.method).toBe('GET')
  })

  it('非 2xx 响应抛错且消息含状态码', async () => {
    const fn: MemoryFetchLike = vi.fn(async () =>
      new Response('boom', { status: 500, statusText: 'Server Error' })
    ) as unknown as MemoryFetchLike
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    await expect(api.listMemoryItems()).rejects.toThrow(/500/)
  })

  it('暴露内部 request helper（advanced 用）', async () => {
    const { fn } = makeFetchMock({
      '/api/memory/custom-path': { status: 200, body: { ok: true } }
    })
    const api = createMemoryDashboardApi({ fetchImpl: fn })
    const r = await api.request<{ ok: boolean }>('/memory/custom-path')
    expect(r.ok).toBe(true)
  })
})

describe('formatImportance', () => {
  it('0.85 → "85.0%"', () => {
    expect(formatImportance(0.85)).toBe('85.0%')
  })
  it('null/undefined → "—"', () => {
    expect(formatImportance(null)).toBe('—')
    expect(formatImportance(undefined)).toBe('—')
  })
})

describe('MEMORY_TYPE_LABELS / MEMORY_STATUS_LABELS', () => {
  it('type 标签含 5 项（user/feedback/project/reference/task）', () => {
    expect(Object.keys(MEMORY_TYPE_LABELS)).toEqual([
      'user',
      'feedback',
      'project',
      'reference',
      'task'
    ])
    expect(MEMORY_TYPE_LABELS.user).toBe('用户')
  })
  it('status 标签含 4 项（active/pending/archived/expired）', () => {
    expect(Object.keys(MEMORY_STATUS_LABELS)).toEqual([
      'active',
      'pending',
      'archived',
      'expired'
    ])
    expect(MEMORY_STATUS_LABELS.active).toBe('活跃')
  })
})

describe('computeMemorySummary', () => {
  it('空数组 → total=0 active=0 archived=0 avg_importance=0', () => {
    const r = computeMemorySummary([])
    expect(r).toEqual({ total: 0, active: 0, archived: 0, avg_importance: 0 })
  })
  it('3 条记忆：1 active + 1 archived + 1 pending → active=1, archived=1, avg=(0.8+0.4+0.6)/3', () => {
    const r = computeMemorySummary([
      { ...fakeItem, status: 'active', importance: 0.8 },
      { ...fakeItem, id: 'm2', status: 'archived', importance: 0.4 },
      { ...fakeItem, id: 'm3', status: 'pending', importance: 0.6 }
    ])
    expect(r.total).toBe(3)
    expect(r.active).toBe(1)
    expect(r.archived).toBe(1)
    expect(r.avg_importance).toBeCloseTo((0.8 + 0.4 + 0.6) / 3, 5)
  })
})
