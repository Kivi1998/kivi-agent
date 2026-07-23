// CodingSummaryCard 组件测试（3 场景：null / 1 metric / 4 metrics + 格式）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CodingSummaryCard from './CodingSummaryCard.vue'
import type { CodingSummary } from '@/types/api'

describe('CodingSummaryCard', () => {
  it('summary=null：4 个 metric 全部显示 "—"', () => {
    const wrapper = mount(CodingSummaryCard, { props: { summary: null } })
    expect(wrapper.find('[data-testid="coding-summary-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cmetric-completion"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="cmetric-tests-passed"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="cmetric-iterations"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="cmetric-recovery"]').text()).toContain('—')
    expect(
      wrapper.find('[data-testid="coding-summary-card"]').attributes('data-loading')
    ).toBe('false')
  })

  it('有数据：渲染 4 个 metric + 百分比 / 1 位小数格式', () => {
    const s: CodingSummary = {
      run_count: 5,
      task_completion_rate: 1.0,
      tests_passed_rate: 0.85,
      avg_iteration_count: 2.1,
      avg_time_to_first_pass_s: 5.5,
      self_recovery_rate: 0.7
    }
    const wrapper = mount(CodingSummaryCard, { props: { summary: s } })
    expect(wrapper.findAll('[data-testid^="cmetric-"]')).toHaveLength(4)
    expect(wrapper.find('[data-testid="cmetric-completion"]').text()).toContain(
      '100.0%'
    )
    expect(wrapper.find('[data-testid="cmetric-tests-passed"]').text()).toContain(
      '85.0%'
    )
    expect(wrapper.find('[data-testid="cmetric-iterations"]').text()).toContain(
      '2.1'
    )
    expect(wrapper.find('[data-testid="cmetric-recovery"]').text()).toContain(
      '70.0%'
    )
  })

  it('loading=true：data-loading 反映 + 0 数据正确显示', () => {
    const s: CodingSummary = {
      run_count: 0,
      task_completion_rate: 0,
      tests_passed_rate: 0,
      avg_iteration_count: 0,
      avg_time_to_first_pass_s: 0,
      self_recovery_rate: 0
    }
    const wrapper = mount(CodingSummaryCard, {
      props: { summary: s, loading: true }
    })
    expect(
      wrapper.find('[data-testid="coding-summary-card"]').attributes('data-loading')
    ).toBe('true')
    expect(wrapper.find('[data-testid="cmetric-completion"]').text()).toContain(
      '0.0%'
    )
    expect(wrapper.find('[data-testid="cmetric-iterations"]').text()).toContain('0.0')
  })
})
