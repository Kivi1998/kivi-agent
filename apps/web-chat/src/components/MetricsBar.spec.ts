// MetricsBar 组件测试（3 场景：null / 1 指标 / 完整 metrics）
import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import MetricsBar from './MetricsBar.vue'
import type { MetricsReport } from '@/types/api'

function makeMetrics(overrides: Partial<MetricsReport['metrics']> = {}): MetricsReport {
  return {
    dataset_name: 'basic-routing-10cases',
    case_count: 5,
    generated_at: '2026-07-23T00:00:00Z',
    metrics: {
      task_success_rate: { rate: 0.8, passed: 4, total: 5 },
      route_accuracy: { rate: 1.0, matched: 5, applicable: 5 },
      tool_selection_accuracy: {
        exact_match_rate: 0.6,
        contain_match_rate: 0.8,
        applicable: 5
      },
      rag_citation_accuracy: { rate: 0.5, matched: 2, applicable: 4 },
      avg_latency_seconds: { avg_s: 2.3, p50_s: 1.5, p95_s: 4.0, count: 5 },
      total_tokens: { input: 500, output: 1000, cache_read: 100, total: 1600 },
      total_cost_usd: { total_usd: 0.05, model: 'gpt-4o-mini', per_case_avg_usd: 0.01 },
      ...overrides
    }
  }
}

describe('MetricsBar', () => {
  it('metrics=null：显示 "暂无指标" empty state + 不渲染 VChart', () => {
    const wrapper = shallowMount(MetricsBar, {
      props: { metrics: null, title: 'test' }
    })
    expect(wrapper.find('[data-testid="metrics-bar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="metrics-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="metrics-chart"]').exists()).toBe(false)
  })

  it('完整 metrics：渲染 VChart + option 包含 7 个 bar name + 7 个 value', () => {
    const wrapper = shallowMount(MetricsBar, {
      props: { metrics: makeMetrics(), title: 'run-1' }
    })
    expect(wrapper.find('[data-testid="metrics-chart"]').exists()).toBe(true)
    const vchart = wrapper.findComponent({ name: 'echarts' })
    expect(vchart.exists()).toBe(true)
    const opt = vchart.props('option') as {
      yAxis: { data: string[] }
      series: Array<{ data: number[] }>
    }
    // 7 个 bar 名称
    expect(opt.yAxis.data).toEqual([
      '任务成功率',
      '路由正确率',
      'Tool 精确匹配',
      'Tool 包含匹配',
      'RAG 引用',
      '平均延迟(s)',
      '总成本(USD)'
    ])
    // 7 个 value：5 个百分比 + 延迟 + 成本
    expect(opt.series[0]?.data).toEqual([0.8, 1.0, 0.6, 0.8, 0.5, 2.3, 0.05])
  })

  it('title prop 透传到 ECharts option.title.text', () => {
    const wrapper = shallowMount(MetricsBar, {
      props: { metrics: makeMetrics(), title: '全局汇总' }
    })
    const vchart = wrapper.findComponent({ name: 'echarts' })
    const opt = vchart.props('option') as { title: { text: string } }
    expect(opt.title.text).toBe('全局汇总')
  })
})
