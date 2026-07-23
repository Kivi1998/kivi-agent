import { describe, it, expect } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import ChartWidget from './ChartWidget.vue'
import type { ChartRenderedEvent } from '../types/api'

/** 构造 1 个 bar chart option */
function makeBarEvent(overrides: Partial<ChartRenderedEvent> = {}): ChartRenderedEvent {
  return {
    type: 'chart.rendered',
    run_id: 'run-chart-1',
    chart_id: 'bar-001',
    option_dict: {
      type: 'bar',
      title: { text: 'Q1-Q3 销售统计' },
      xAxis: { type: 'category', data: ['Q1', 'Q2', 'Q3'] },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: [10, 20, 30] }],
    },
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

/** 构造 1 个 line chart option */
function makeLineEvent(overrides: Partial<ChartRenderedEvent> = {}): ChartRenderedEvent {
  return {
    type: 'chart.rendered',
    run_id: 'run-chart-2',
    chart_id: 'line-001',
    option_dict: {
      type: 'line',
      title: { text: '趋势' },
      xAxis: { type: 'category', data: ['1月', '2月', '3月'] },
      yAxis: { type: 'value' },
      series: [{ type: 'line', data: [5, 15, 25] }],
    },
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

describe('ChartWidget', () => {
  it('bar chart：option_dict 完整透传给 VChart（含 type/title/xAxis/yAxis/series）', () => {
    const wrapper = shallowMount(ChartWidget, {
      props: { event: makeBarEvent() },
    })

    expect(wrapper.find('[data-testid="chart-widget"]').exists()).toBe(true)
    expect(
      wrapper.find('[data-testid="chart-widget"]').attributes('data-chart-id'),
    ).toBe('bar-001')
    expect(
      wrapper.find('[data-testid="chart-widget"]').attributes('data-chart-type'),
    ).toBe('bar')

    // 标题栏展示 chart_id + type
    expect(wrapper.text()).toContain('图表: bar-001')
    expect(wrapper.text()).toContain('type=bar')
    expect(wrapper.text()).toContain('run_id=run-chart-1')

    // option 透传：找 VChart 子组件，验证 props.option 是同一个引用
    // vue-echarts 默认导出的组件 name 是 "echarts"（见 dist/index.js）
    const vchart = wrapper.findComponent({ name: 'echarts' })
    expect(vchart.exists()).toBe(true)
    const optionProp = vchart.props('option') as Record<string, unknown>
    expect(optionProp.type).toBe('bar')
    expect(optionProp.title).toEqual({ text: 'Q1-Q3 销售统计' })
    expect(optionProp.series).toEqual([{ type: 'bar', data: [10, 20, 30] }])
  })

  it('line chart：option_dict 完整透传给 VChart', () => {
    const wrapper = shallowMount(ChartWidget, {
      props: { event: makeLineEvent() },
    })

    expect(
      wrapper.find('[data-testid="chart-widget"]').attributes('data-chart-type'),
    ).toBe('line')

    const vchart = wrapper.findComponent({ name: 'echarts' })
    const optionProp = vchart.props('option') as Record<string, unknown>
    expect(optionProp.type).toBe('line')
    expect(optionProp.xAxis).toEqual({ type: 'category', data: ['1月', '2月', '3月'] })
    expect(optionProp.series).toEqual([{ type: 'line', data: [5, 15, 25] }])
  })

  it('option_dict 缺失 type 字段时，data-chart-type 退化为 "unknown"', () => {
    const wrapper = shallowMount(ChartWidget, {
      props: {
        event: makeBarEvent({
          option_dict: {
            title: { text: 'no type field' },
            xAxis: { type: 'category', data: ['a', 'b'] },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: [1, 2] }],
          },
        }),
      },
    })

    expect(
      wrapper.find('[data-testid="chart-widget"]').attributes('data-chart-type'),
    ).toBe('unknown')
    // 仍然透传 option（不报错）
    const vchart = wrapper.findComponent({ name: 'echarts' })
    expect(vchart.props('option')).toBeDefined()
  })

  it('option_dict 非对象（如 string）时，使用占位 option 兜底', () => {
    const wrapper = shallowMount(ChartWidget, {
      props: {
        event: makeBarEvent({
          option_dict: 'invalid-string' as unknown as Record<string, unknown>,
        }),
      },
    })

    const vchart = wrapper.findComponent({ name: 'echarts' })
    const optionProp = vchart.props('option') as Record<string, unknown>
    // 兜底 option：title + 空 data
    expect(optionProp.title).toEqual({ text: '(invalid option_dict)', left: 'center' })
    expect(Array.isArray(optionProp.series)).toBe(true)
    expect((optionProp.series as unknown[]).length).toBe(0)
  })
})
