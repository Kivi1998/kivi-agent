// SummaryCard 组件测试（3 场景：空 / 1 metric / 4 metrics）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCard from './SummaryCard.vue'
import type { Summary } from '@/types/api'

describe('SummaryCard', () => {
  it('summary=null：4 个 metric 全部显示 "—"', () => {
    const wrapper = mount(SummaryCard, { props: { summary: null } })
    expect(wrapper.find('[data-testid="summary-card"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="metric-success-rate"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="metric-avg-latency"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="metric-total-tokens"]').text()).toContain('—')
    expect(wrapper.find('[data-testid="metric-total-cost"]').text()).toContain('—')
    // data-loading 默认 false
    expect(
      wrapper.find('[data-testid="summary-card"]').attributes('data-loading')
    ).toBe('false')
  })

  it('1 个 metric：渲染所有 4 个 tile + data-testid 各自独立', () => {
    const s: Summary = {
      case_count: 1,
      success_rate: 1.0,
      avg_latency_s: 1.0,
      total_tokens: 100,
      total_cost_usd: 0.001
    }
    const wrapper = mount(SummaryCard, { props: { summary: s } })
    expect(wrapper.findAll('[data-testid^="metric-"]')).toHaveLength(4)
    expect(wrapper.find('[data-testid="metric-success-rate"]').text()).toContain(
      '100.0%'
    )
    expect(wrapper.find('[data-testid="metric-avg-latency"]').text()).toContain(
      '1.00s'
    )
    expect(wrapper.find('[data-testid="metric-total-tokens"]').text()).toContain(
      '100'
    )
    expect(wrapper.find('[data-testid="metric-total-cost"]').text()).toContain(
      '$0.0010'
    )
  })

  it('4 个 metric：千分位 / 美元格式正确 + loading 状态反映', () => {
    const s: Summary = {
      case_count: 12345,
      success_rate: 0.836,
      avg_latency_s: 2.3456,
      total_tokens: 1234567,
      total_cost_usd: 12.5
    }
    const wrapper = mount(SummaryCard, {
      props: { summary: s, loading: true }
    })
    // 成功率 83.6% → 1 位小数
    expect(wrapper.find('[data-testid="metric-success-rate"]').text()).toContain(
      '83.6%'
    )
    // 延迟 2.35s → 2 位小数
    expect(wrapper.find('[data-testid="metric-avg-latency"]').text()).toContain(
      '2.35s'
    )
    // token 千分位
    expect(wrapper.find('[data-testid="metric-total-tokens"]').text()).toContain(
      '1,234,567'
    )
    // 成本 4 位小数
    expect(wrapper.find('[data-testid="metric-total-cost"]').text()).toContain(
      '$12.5000'
    )
    // loading=true 反映
    expect(
      wrapper.find('[data-testid="summary-card"]').attributes('data-loading')
    ).toBe('true')
  })
})
