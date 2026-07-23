// MemberOutcomesTable 组件测试（3 场景：空 / 1 行 + 点击 / 多行 + 答案摘要截断）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemberOutcomesTable from './MemberOutcomesTable.vue'
import type { MemberOutcome } from '@/types/api'

const base: MemberOutcome = {
  member_id: 'researcher',
  role: 'research',
  success: true,
  steps: 5,
  tool_calls: 3,
  finished_at: '2026-07-23T00:00:30Z',
  final_answer: 'ok'
}

describe('MemberOutcomesTable', () => {
  it('空：显示 "暂无成员结果" empty state + 不渲染 grid', () => {
    const wrapper = mount(MemberOutcomesTable, { props: { outcomes: [] } })
    expect(wrapper.find('[data-testid="member-outcomes-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="member-outcomes-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="member-outcomes-grid"]').exists()).toBe(false)
  })

  it('1 行：渲染 1 行 + 显示 role + steps + tool_calls + 点击触发 select', async () => {
    const wrapper = mount(MemberOutcomesTable, { props: { outcomes: [base] } })
    expect(wrapper.findAll('[data-testid^="member-outcome-row-"]')).toHaveLength(1)
    const row = wrapper.find('[data-testid="member-outcome-row-researcher"]')
    expect(row.text()).toContain('research')
    expect(row.text()).toContain('5')
    expect(row.text()).toContain('3')
    expect(row.text()).toContain('ok')

    await row.trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['researcher'])
  })

  it('多行：失败显示 ✗ + final_answer >80 字 截断为 80+…', () => {
    const longAns = 'a'.repeat(100)
    const outcomes: MemberOutcome[] = [
      base,
      {
        ...base,
        member_id: 'writer',
        role: 'writer',
        success: false,
        final_answer: longAns
      }
    ]
    const wrapper = mount(MemberOutcomesTable, { props: { outcomes } })
    const rows = wrapper.findAll('[data-testid^="member-outcome-row-"]')
    expect(rows).toHaveLength(2)
    expect(rows[1]?.text()).toContain('✗')
    // 100 字符截前 80 + '…'
    const txt = rows[1]?.text() ?? ''
    expect(txt).toContain('…')
    // 检查最终答案 80 个 a + …
    const aBlock = 'a'.repeat(80) + '…'
    expect(txt).toContain(aBlock)
  })
})
