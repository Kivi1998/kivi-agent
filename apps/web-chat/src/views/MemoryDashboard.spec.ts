// MemoryDashboard view 测试（2 场景：空 list + 错误处理 / 有数据 + select 加载 detail + 搜索）
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import MemoryDashboard from './MemoryDashboard.vue'
import type { MemoryFetchLike } from '@/api/memory'
import type { MemoryItem, MemorySearchResult } from '@/types/api'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/dashboard/memory',
        name: 'memory-dashboard',
        component: { template: '<div/>' }
      }
    ]
  })
}

function makeFetch(
  responses: Record<string, { status: number; body: unknown }>
): { fn: MemoryFetchLike; urls: string[] } {
  const urls: string[] = []
  const fn: MemoryFetchLike = async (input) => {
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

const fakeItems: MemoryItem[] = [
  {
    id: 'mem-1',
    content: '用户偏好中文回复',
    memory_type: 'user',
    importance: 0.85,
    status: 'active',
    source: 'session-abc',
    created_at: '2026-07-23T00:00:00Z',
    expires_at: null,
    updated_at: null
  },
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

const fakeDetail = { item: fakeItems[0] }
const fakeAudit = { memory_id: 'mem-1', events: [] }
const fakeSearchResults: MemorySearchResult[] = [
  {
    id: 'mem-1',
    content: '用户偏好中文回复',
    score: 0.9,
    memory_type: 'user',
    importance: 0.85,
    status: 'active',
    source: 'session-abc',
    created_at: '2026-07-23T00:00:00Z'
  }
]

describe('MemoryDashboard view', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('空 list + 错误处理：500 响应在视图顶部显示 error', async () => {
    const { fn } = makeFetch({})
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/memory')
      await router.isReady()
      const wrapper = mount(MemoryDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="memory-dashboard"]').exists()).toBe(true)
      // /api/memory/items 没有 mock → 404 → 抛错 → 视图渲染 error banner
      expect(wrapper.find('[data-testid="memory-dashboard-error"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="memory-list-empty"]').exists()).toBe(true)
    } finally {
      global.fetch = orig
    }
  })

  it('有数据：list 渲染 + select 行加载 detail + audit + 搜索触发 search API', async () => {
    const { fn, urls } = makeFetch({
      '/api/memory/items?limit=100': { status: 200, body: { total: 2, items: fakeItems } },
      '/api/memory/items/mem-1': { status: 200, body: fakeDetail },
      '/api/memory/audit?memory_id=mem-1': { status: 200, body: fakeAudit },
      '/api/memory/search?q=%E7%94%A8%E6%88%B7%E5%81%8F%E5%A5%BD&top_k=5': {
        status: 200,
        body: { query: '用户偏好', top_k: 5, results: fakeSearchResults }
      }
    })
    const orig = global.fetch
    global.fetch = fn as unknown as typeof fetch
    try {
      const router = makeRouter()
      router.push('/dashboard/memory')
      await router.isReady()
      const wrapper = mount(MemoryDashboard, {
        global: { plugins: [router] }
      })
      await flushPromises()
      await flushPromises()

      // list 渲染 2 行
      expect(wrapper.findAll('[data-testid^="memory-row-"]')).toHaveLength(2)

      // 提交搜索
      const searchInput = wrapper.find('[data-testid="memory-search-input"]')
      await searchInput.setValue('用户偏好')
      // 直接在 search 子组件上触发 form submit
      const searchForm = wrapper.find('[data-testid="memory-search-form"]')
      await searchForm.trigger('submit')
      await flushPromises()
      await flushPromises()

      // 搜索结果渲染
      expect(wrapper.findAll('[data-testid^="memory-search-hit-mem-"]')).toHaveLength(1)

      // 确认 search API 被调用
      expect(urls.some((u) => u.includes('/api/memory/search'))).toBe(true)

      // 点击 list 中的 mem-1 加载 detail + audit
      await wrapper.find('[data-testid="memory-row-mem-1"]').trigger('click')
      await flushPromises()
      await flushPromises()
      expect(wrapper.find('[data-testid="memory-detail-id"]').text()).toBe('mem-1')
      expect(urls.some((u) => u.includes('/api/memory/items/mem-1'))).toBe(true)
      expect(urls.some((u) => u.includes('/api/memory/audit?memory_id=mem-1'))).toBe(true)
    } finally {
      global.fetch = orig
    }
  })
})
