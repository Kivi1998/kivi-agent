// TeamsList 组件测试（3 场景：空 / 1 team / 多 team + 点击事件）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TeamsList from './TeamsList.vue'
import type { TeamSummaryItem } from '@/types/api'

const baseTeam: TeamSummaryItem = {
  team_id: 'team-1',
  goal: '调研并对比 X 和 Y 框架',
  member_count: 3,
  success: true,
  created_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:01:00Z'
}

describe('TeamsList', () => {
  it('空：显示 "暂无 team 计划" empty state + 不显示 table', () => {
    const wrapper = mount(TeamsList, { props: { teams: [] } })
    expect(wrapper.find('[data-testid="teams-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="teams-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="teams-table"]').exists()).toBe(false)
  })

  it('1 team：渲染 1 行 + 显示 goal + success badge', () => {
    const wrapper = mount(TeamsList, { props: { teams: [baseTeam] } })
    expect(wrapper.findAll('[data-testid^="teams-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="teams-row-team-1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('调研并对比')
    expect(wrapper.find('[data-testid="teams-row-team-1"]').text()).toContain('✓')
    expect(wrapper.find('[data-testid="teams-count"]').text()).toContain('1')
  })

  it('多 team：渲染多行 + 点击行触发 select 事件 + null created_at 显示占位', async () => {
    const teams: TeamSummaryItem[] = [
      baseTeam,
      {
        ...baseTeam,
        team_id: 'team-2',
        goal: '写一份报告',
        success: false,
        created_at: null
      }
    ]
    const wrapper = mount(TeamsList, { props: { teams } })
    expect(wrapper.findAll('[data-testid^="teams-row-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="teams-row-team-2"]').text()).toContain(
      '(未开始)'
    )
    expect(wrapper.find('[data-testid="teams-row-team-2"]').text()).toContain('✗')

    // 点击 team-1 触发 select
    await wrapper.find('[data-testid="teams-row-team-1"]').trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['team-1'])

    // 点击 team-2 也触发
    await wrapper.find('[data-testid="teams-row-team-2"]').trigger('click')
    const emitted2 = wrapper.emitted('select')
    expect(emitted2?.[1]).toEqual(['team-2'])
  })
})
