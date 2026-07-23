// RoleTimeline 组件测试（3 场景：空 / 1 成员 / 多成员 + 排序 + success badge）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RoleTimeline from './RoleTimeline.vue'
import type { MemberOutcome } from '@/types/api'

const baseMember: MemberOutcome = {
  member_id: 'researcher',
  role: 'research',
  success: true,
  steps: 5,
  tool_calls: 3,
  finished_at: '2026-07-23T00:00:30Z',
  final_answer: 'ok'
}

describe('RoleTimeline', () => {
  it('空：显示 "暂无成员" empty state + 不渲染 table', () => {
    const wrapper = mount(RoleTimeline, { props: { members: [] } })
    expect(wrapper.find('[data-testid="role-timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="role-timeline-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="role-timeline-table"]').exists()).toBe(false)
  })

  it('1 成员：渲染 1 行 + 显示 member_id + role + 步数 + 工具数 + success badge', () => {
    const wrapper = mount(RoleTimeline, { props: { members: [baseMember] } })
    expect(wrapper.findAll('[data-testid^="role-timeline-row-"]')).toHaveLength(1)
    const row = wrapper.find('[data-testid="role-timeline-row-researcher"]')
    expect(row.text()).toContain('researcher')
    expect(row.text()).toContain('research')
    expect(row.text()).toContain('5')
    expect(row.text()).toContain('3')
    expect(row.text()).toContain('✓')
    expect(row.attributes('data-success')).toBe('true')
  })

  it('多成员：按 member_id 字母序排序 + failure 渲染 ✗ + null finished_at 显示占位', () => {
    const members: MemberOutcome[] = [
      { ...baseMember, member_id: 'writer' },
      { ...baseMember, member_id: 'alpha', role: 'planner' },
      {
        ...baseMember,
        member_id: 'beta',
        success: false,
        finished_at: null
      }
    ]
    const wrapper = mount(RoleTimeline, { props: { members } })
    const rows = wrapper.findAll('[data-testid^="role-timeline-row-"]')
    expect(rows).toHaveLength(3)
    // 按字母序：alpha, beta, writer
    expect(rows[0]?.attributes('data-testid')).toBe('role-timeline-row-alpha')
    expect(rows[1]?.attributes('data-testid')).toBe('role-timeline-row-beta')
    expect(rows[2]?.attributes('data-testid')).toBe('role-timeline-row-writer')
    // beta 失败 → ✗
    expect(rows[1]?.text()).toContain('✗')
    expect(rows[1]?.text()).toContain('(进行中)')
    expect(rows[1]?.attributes('data-success')).toBe('false')
  })
})
