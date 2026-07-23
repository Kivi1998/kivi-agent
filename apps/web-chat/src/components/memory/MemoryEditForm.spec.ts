// MemoryEditForm 组件测试（3 场景：创建模式 / 编辑模式回填 / 提交 emit）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemoryEditForm from './MemoryEditForm.vue'
import type { MemoryItem } from '@/types/api'

const editItem: MemoryItem = {
  id: 'mem-1',
  content: '原内容',
  memory_type: 'feedback',
  importance: 0.7,
  status: 'pending',
  source: 'session-edit',
  created_at: '2026-07-23T00:00:00Z',
  expires_at: '2026-12-31T15:30:00Z',
  updated_at: null
}

describe('MemoryEditForm', () => {
  it('item=null：创建模式（title="新建记忆" + 全部字段为空）', () => {
    const wrapper = mount(MemoryEditForm, { props: { item: null } })
    expect(wrapper.find('[data-testid="memory-edit-form"]').attributes('data-mode')).toBe(
      'create'
    )
    expect(wrapper.text()).toContain('新建记忆')
    expect((wrapper.find('[data-testid="memory-form-content"]').element as HTMLTextAreaElement).value).toBe('')
    // 提交按钮文字 "创建"
    expect(wrapper.find('[data-testid="memory-form-submit"]').text()).toBe('创建')
  })

  it('item 有值：编辑模式（回填 + status 字段出现 + 提交按钮 "保存"）', () => {
    const wrapper = mount(MemoryEditForm, { props: { item: editItem } })
    expect(wrapper.find('[data-testid="memory-edit-form"]').attributes('data-mode')).toBe(
      'edit'
    )
    expect(wrapper.text()).toContain('编辑记忆')
    // content 回填
    expect(
      (wrapper.find('[data-testid="memory-form-content"]').element as HTMLTextAreaElement).value
    ).toBe('原内容')
    // type 回填（feedback → "反馈"）
    expect(
      (wrapper.find('[data-testid="memory-form-type"]').element as HTMLSelectElement).value
    ).toBe('feedback')
    // status 字段仅在编辑模式渲染
    expect(wrapper.find('[data-testid="memory-form-status"]').exists()).toBe(true)
    expect(
      (wrapper.find('[data-testid="memory-form-status"]').element as HTMLSelectElement).value
    ).toBe('pending')
    // source 回填
    expect(
      (wrapper.find('[data-testid="memory-form-source"]').element as HTMLInputElement).value
    ).toBe('session-edit')
    // 提交按钮文字 "保存"
    expect(wrapper.find('[data-testid="memory-form-submit"]').text()).toBe('保存')
  })

  it('创建模式提交：content 必填 + submit emit (payload, isEdit=false) + 取消 emit', async () => {
    const wrapper = mount(MemoryEditForm, { props: { item: null } })
    // content 为空时，submit 按钮 disabled
    const btn = wrapper.find('[data-testid="memory-form-submit"]')
    expect((btn.element as HTMLButtonElement).disabled).toBe(true)

    // 填 content
    await wrapper.find('[data-testid="memory-form-content"]').setValue('新记忆内容')
    // 改 type
    await wrapper.find('[data-testid="memory-form-type"]').setValue('task')
    // 改 importance
    const imp = wrapper.find('[data-testid="memory-form-importance"]')
    await imp.setValue('0.9')
    // 改 source
    await wrapper.find('[data-testid="memory-form-source"]').setValue('session-1')

    expect((btn.element as HTMLButtonElement).disabled).toBe(false)
    // 通过 form submit 触发（button type=submit）
    await wrapper.find('form').trigger('submit')

    const submitEvents = wrapper.emitted('submit')
    expect(submitEvents).toBeTruthy()
    expect(submitEvents?.[0]?.[1]).toBe(false)
    const payload = submitEvents?.[0]?.[0] as Record<string, unknown>
    expect(payload.content).toBe('新记忆内容')
    expect(payload.memory_type).toBe('task')
    expect(payload.importance).toBe(0.9)
    expect(payload.source).toBe('session-1')

    // 取消
    await wrapper.find('[data-testid="memory-form-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')?.[0]).toBeTruthy()
  })
})
