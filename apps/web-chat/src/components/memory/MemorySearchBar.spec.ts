// MemorySearchBar 组件测试（3 场景：空 / 有结果 + render / submit emit + top_k + 点击结果）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemorySearchBar from './MemorySearchBar.vue'
import type { MemorySearchResult } from '@/types/api'

const fakeResults: MemorySearchResult[] = [
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
    score: 0.71,
    memory_type: 'feedback',
    importance: 0.6,
    status: 'pending',
    source: 'session-xyz',
    created_at: '2026-07-22T00:00:00Z'
  }
]

describe('MemorySearchBar', () => {
  it('空：显示 "暂无检索结果" + 不显示结果列表', () => {
    const wrapper = mount(MemorySearchBar, { props: { results: [] } })
    expect(wrapper.find('[data-testid="memory-search-bar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-search-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-search-results"]').exists()).toBe(false)
  })

  it('有结果：渲染 list + score 百分比 + type/status badge', () => {
    const wrapper = mount(MemorySearchBar, { props: { results: fakeResults } })
    expect(wrapper.findAll('[data-testid^="memory-search-hit-mem-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="memory-search-hit-mem-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-search-hit-mem-2"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('92.0%')
    expect(wrapper.text()).toContain('71.0%')
    expect(wrapper.text()).toContain('用户')
    expect(wrapper.text()).toContain('反馈')
  })

  it('提交 emit search + top_k 滑块 + 点击结果 emit select', async () => {
    const wrapper = mount(MemorySearchBar, { props: { results: fakeResults } })
    // 输入查询词
    await wrapper.find('[data-testid="memory-search-input"]').setValue('用户偏好')
    // top_k 默认 5
    const topk = wrapper.find('[data-testid="memory-search-topk"]')
    await topk.setValue('10')
    expect(wrapper.find('[data-testid="memory-search-topk-value"]').text()).toBe('10')

    // 提交（通过 form submit 触发）
    await wrapper.find('form').trigger('submit')
    const searchEvents = wrapper.emitted('search')
    expect(searchEvents?.[0]).toEqual([{ q: '用户偏好', topK: 10 }])

    // 点击结果
    await wrapper.find('[data-testid="memory-search-hit-mem-1"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['mem-1'])
  })
})
