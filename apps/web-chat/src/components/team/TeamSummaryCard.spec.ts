// TeamSummaryCard 组件测试（3 场景：null / 1 metric / 4 metrics + 格式）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TeamSummaryCard from './TeamSummaryCard.vue'
import type { TeamSummary } from '@/types/api'

describe('TeamSummaryCard', () => {
  it('summary=null：4 个 metric 全部显示 "—"', () => {
    const wrapper = mount(TeamSummaryCard, { props: { summary: null } })
    expect(wrapper.find('[data-testid="team-summary-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tmetric-success-rate"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="tmetric-delegation"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="tmetric-handoff"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="tmetric-latency"]').text()).toContain('—')
    expect(
      wrapper.find('[data-testid="team-summary-card"]').attributes('data-loading')
    ).toBe('false')
  })

  it('有数据：渲染 4 个 metric + 百分比 / 秒格式', () => {
    const s: TeamSummary = {
      team_count: 3,
      success_rate: 1.0,
      avg_delegation_accuracy: 0.9,
      avg_handoff_quality: 0.8,
      avg_coordination_latency_s: 12.5,
      avg_agent_utilization: 0.7
    }
    const wrapper = mount(TeamSummaryCard, { props: { summary: s } })
    expect(wrapper.findAll('[data-testid^="tmetric-"]')).toHaveLength(4)
    expect(wrapper.find('[data-testid="tmetric-success-rate"]').text()).toContain(
      '100.0%'
    )
    expect(wrapper.find('[data-testid="tmetric-delegation"]').text()).toContain(
      '90.0%'
    )
    expect(wrapper.find('[data-testid="tmetric-handoff"]').text()).toContain(
      '80.0%'
    )
    expect(wrapper.find('[data-testid="tmetric-latency"]').text()).toContain(
      '12.50s'
    )
  })

  it('loading=true：data-loading 反映', () => {
    const s: TeamSummary = {
      team_count: 1,
      success_rate: 0,
      avg_delegation_accuracy: 0,
      avg_handoff_quality: 0,
      avg_coordination_latency_s: 0,
      avg_agent_utilization: 0
    }
    const wrapper = mount(TeamSummaryCard, {
      props: { summary: s, loading: true }
    })
    expect(
      wrapper.find('[data-testid="team-summary-card"]').attributes('data-loading')
    ).toBe('true')
    // 0% 也正确渲染
    expect(wrapper.find('[data-testid="tmetric-success-rate"]').text()).toContain(
      '0.0%'
    )
  })
})
