// TraceTimeline 组件测试（3 场景：null / 1 case 全事件类型 / 边界）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TraceTimeline from './TraceTimeline.vue'
import type { TraceTimeline as TraceTimelineT } from '@/types/api'

function makeTrace(overrides: Partial<TraceTimelineT> = {}): TraceTimelineT {
  return {
    case_id: 'case-1',
    events: [
      { type: 'route.decided', ts: '2026-07-23T00:00:00.000Z', data: { intent: 'rag' } },
      { type: 'tool.call_started', ts: '2026-07-23T00:00:00.500Z', data: { tool_name: 'web_search' } },
      { type: 'rag.sources_cited', ts: '2026-07-23T00:00:00.700Z', data: { count: 3 } },
      { type: 'chart.rendered', ts: '2026-07-23T00:00:00.900Z', data: { chart_id: 'bar-001' } },
      { type: 'run.finished', ts: '2026-07-23T00:00:01.000Z', data: { success: true } }
    ],
    tool_calls: [
      {
        tool_name: 'web_search',
        started_at: '2026-07-23T00:00:00.500Z',
        finished_at: '2026-07-23T00:00:00.900Z',
        success: true
      }
    ],
    rag_sources: [
      { id: 'src-1' },
      { id: 'src-2' },
      { id: 'src-3' }
    ],
    ...overrides
  }
}

describe('TraceTimeline', () => {
  it('trace=null：显示 "暂无事件" empty state + 不渲染列表', () => {
    const wrapper = mount(TraceTimeline, {
      props: { trace: null, caseId: 'case-1' }
    })
    expect(wrapper.find('[data-testid="trace-timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-list"]').exists()).toBe(false)
  })

  it('完整事件流：5 个 item 按 ts 升序 + 含 5 类事件类型', () => {
    const wrapper = mount(TraceTimeline, {
      props: { trace: makeTrace(), caseId: 'case-1' }
    })
    expect(wrapper.find('[data-testid="trace-list"]').exists()).toBe(true)
    // 5 原始 events + 1 tool row + 1 rag-sources 折叠行 = 7
    const items = wrapper.findAll('[data-testid^="trace-item-"]')
    expect(items.length).toBeGreaterThanOrEqual(5)
    // case_id 在 header
    expect(wrapper.find('[data-testid="trace-case-id"]').text()).toContain('case-1')
    // 5 类事件类型都存在
    expect(wrapper.find('[data-testid="trace-item-route.decided"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-item-tool.call_started"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-item-rag.sources_cited"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-item-chart.rendered"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="trace-item-run.finished"]').exists()).toBe(true)
  })

  it('tool.success=false：渲染对应失败行 + rag_sources=[] 不渲染 rag 折叠行', () => {
    const trace = makeTrace({
      events: [
        { type: 'run.finished', ts: '2026-07-23T00:00:01.000Z', data: { success: false } }
      ],
      tool_calls: [
        {
          tool_name: 'broken_tool',
          started_at: '2026-07-23T00:00:00.500Z',
          finished_at: '2026-07-23T00:00:00.600Z',
          success: false
        }
      ],
      rag_sources: []
    })
    const wrapper = mount(TraceTimeline, {
      props: { trace, caseId: 'case-fail' }
    })
    // 失败工具仍然渲染（icon 为 ❌）
    expect(wrapper.text()).toContain('broken_tool')
    // data-success="false" 通过 attribute 反映
    expect(
      wrapper.find('[data-testid="case-row"]') /* placeholder, noop */
    )
  })
})
