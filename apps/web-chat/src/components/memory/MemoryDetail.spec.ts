// MemoryDetail 组件测试（3 场景：null / 有 item + 字段渲染 / 3 按钮 emit）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemoryDetail from './MemoryDetail.vue'
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
  updated_at: '2026-07-23T00:01:00Z'
}

describe('MemoryDetail', () => {
  it('item=null：显示 empty 占位 + 不显示 body', () => {
    const wrapper = mount(MemoryDetail, { props: { item: null } })
    expect(wrapper.find('[data-testid="memory-detail-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-detail-body"]').exists()).toBe(false)
  })

  it('有 item：渲染 content + meta + status badge + importance 百分比', () => {
    const wrapper = mount(MemoryDetail, { props: { item: baseItem } })
    expect(wrapper.find('[data-testid="memory-detail-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-detail-id"]').text()).toBe('mem-1')
    expect(wrapper.find('[data-testid="memory-detail-content"]').text()).toBe(
      '用户偏好中文回复'
    )
    expect(wrapper.find('[data-testid="memory-detail-type"]').text()).toBe('用户')
    expect(wrapper.find('[data-testid="memory-detail-status"]').text()).toBe('活跃')
    expect(wrapper.find('[data-testid="memory-detail-importance"]').text()).toBe(
      '85.0%'
    )
    expect(wrapper.find('[data-testid="memory-detail-source"]').text()).toBe(
      'session-abc'
    )
  })

  it('3 按钮 emit：edit / archive / delete + 已归档时隐藏 archive 按钮', async () => {
    const wrapper = mount(MemoryDetail, { props: { item: baseItem } })
    await wrapper.find('[data-testid="memory-detail-edit"]').trigger('click')
    expect(wrapper.emitted('edit')?.[0]).toEqual(['mem-1'])

    await wrapper.find('[data-testid="memory-detail-archive"]').trigger('click')
    expect(wrapper.emitted('archive')?.[0]).toEqual(['mem-1'])

    await wrapper.find('[data-testid="memory-detail-delete"]').trigger('click')
    expect(wrapper.emitted('delete')?.[0]).toEqual(['mem-1'])

    // 当 status=archived 时，archive 按钮不渲染
    const archivedWrapper = mount(MemoryDetail, {
      props: { item: { ...baseItem, status: 'archived' } }
    })
    expect(archivedWrapper.find('[data-testid="memory-detail-archive"]').exists()).toBe(
      false
    )
  })
})
