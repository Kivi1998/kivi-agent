// MemoryList 组件测试（3 场景：空 / 1 item / 多 item + 过滤 emit）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemoryList from './MemoryList.vue'
import type { MemoryItem } from '@/types/api'

const baseItem: MemoryItem = {
  id: 'mem-1',
  content: '用户偏好中文回复',
  memory_type: 'user',
  importance: 0.85,
  status: 'active',
  source: 'session-abc',
  created_at: '2026-07-23T00:00:00Z',
  expires_at: null,
  updated_at: null
}

describe('MemoryList', () => {
  it('空：显示 "暂无记忆" empty state + 不显示 table', () => {
    const wrapper = mount(MemoryList, { props: { items: [] } })
    expect(wrapper.find('[data-testid="memory-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-list-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-list-table"]').exists()).toBe(false)
  })

  it('1 item：渲染 1 行 + 显示 importance 百分比 + status badge', () => {
    const wrapper = mount(MemoryList, { props: { items: [baseItem] } })
    expect(wrapper.findAll('[data-testid^="memory-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="memory-row-mem-1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('mem-1')
    expect(wrapper.text()).toContain('85%')
    expect(wrapper.text()).toContain('活跃')
    expect(wrapper.text()).toContain('session-abc')
    expect(wrapper.find('[data-testid="memory-list-count"]').text()).toContain('1')
  })

  it('多 item + 过滤 emit：render 多行 + 状态过滤 select 触发 update 事件 + 点击行触发 select', async () => {
    const items: MemoryItem[] = [
      baseItem,
      {
        ...baseItem,
        id: 'mem-2',
        memory_type: 'feedback',
        importance: 0.4,
        status: 'archived',
        source: 'session-xyz'
      }
    ]
    const wrapper = mount(MemoryList, {
      props: { items, filterStatus: '', filterType: '', filterSource: '' }
    })
    expect(wrapper.findAll('[data-testid^="memory-row-"]')).toHaveLength(2)
    // mem-2 status=archived → 显示 "已归档"
    expect(wrapper.find('[data-testid="memory-row-mem-2"]').text()).toContain('已归档')

    // 改 status 过滤
    const statusSelect = wrapper.find(
      '[data-testid="memory-filter-status"]'
    )
    await statusSelect.setValue('active')
    expect(wrapper.emitted('update:filterStatus')?.[0]).toEqual(['active'])

    // 改 type 过滤
    const typeSelect = wrapper.find('[data-testid="memory-filter-type"]')
    await typeSelect.setValue('feedback')
    expect(wrapper.emitted('update:filterType')?.[0]).toEqual(['feedback'])

    // 改 source 过滤
    const sourceInput = wrapper.find(
      '[data-testid="memory-filter-source"]'
    )
    await sourceInput.setValue('session-abc')
    expect(wrapper.emitted('update:filterSource')?.[0]).toEqual(['session-abc'])

    // 点击行触发 select
    await wrapper.find('[data-testid="memory-row-mem-1"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual(['mem-1'])
  })
})
