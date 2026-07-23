import { describe, it, expect } from 'vitest'
import { useBusinessEvents } from './useBusinessEvents'
import type {
  RagSourcesCitedEvent,
  ChartRenderedEvent,
  LlmThinkingEvent,
  RouteDecidedEvent,
  RouteDecision,
} from './useBusinessEvents'

/** 构造 1 条 rag.sources_cited 事件（最少字段） */
function makeRagEvent(overrides: Partial<RagSourcesCitedEvent> = {}): RagSourcesCitedEvent {
  return {
    type: 'rag.sources_cited',
    run_id: 'run-1',
    sources: [
      { id: 'kb-001', title: 'RAG 系统架构综述', score: 0.95 },
      { id: 'kb-002', title: '企业内部知识库最佳实践', score: 0.92 },
    ],
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

function makeChartEvent(overrides: Partial<ChartRenderedEvent> = {}): ChartRenderedEvent {
  return {
    type: 'chart.rendered',
    run_id: 'run-1',
    chart_id: 'chart-001',
    option_dict: {
      type: 'bar',
      title: { text: 'Test Bar' },
      xAxis: { type: 'category', data: ['Q1', 'Q2', 'Q3'] },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: [10, 20, 30] }],
    },
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

function makeThinkingEvent(overrides: Partial<LlmThinkingEvent> = {}): LlmThinkingEvent {
  return {
    type: 'llm.thinking',
    run_id: 'run-1',
    step: 1,
    content: 'analyzing query',
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

function makeRouteDecision(overrides: Partial<RouteDecision> = {}): RouteDecision {
  return {
    query: '对比网上关于 RAG 的最新文章和我们内部知识库',
    intent: 'rag',
    target_profiles: ['rag', 'web_search', 'synthesizer'],
    is_multi_intent: true,
    confidence: 0.8,
    matched_keywords: ['网上', '最新', '内部', '知识库'],
    ...overrides,
  }
}

function makeRouteEvent(decision: RouteDecision): RouteDecidedEvent {
  return {
    type: 'route.decided',
    run_id: 'run-1',
    decision,
    ts: '2026-07-23T12:00:00Z',
  }
}

describe('useBusinessEvents', () => {
  describe('onEvent', () => {
    it('rag.sources_cited → 累加到 ragCitations', () => {
      const { ragCitations, onEvent } = useBusinessEvents()
      onEvent(makeRagEvent())
      onEvent(makeRagEvent({ run_id: 'run-2' }))
      expect(ragCitations.value).toHaveLength(2)
      expect(ragCitations.value[0].run_id).toBe('run-1')
      expect(ragCitations.value[1].run_id).toBe('run-2')
    })

    it('chart.rendered → 累加到 chartMetadata', () => {
      const { chartMetadata, onEvent } = useBusinessEvents()
      onEvent(makeChartEvent())
      expect(chartMetadata.value).toHaveLength(1)
      expect(chartMetadata.value[0].chart_id).toBe('chart-001')
    })

    it('llm.thinking → 累加到 thinkingTraces', () => {
      const { thinkingTraces, onEvent } = useBusinessEvents()
      onEvent(makeThinkingEvent())
      expect(thinkingTraces.value).toHaveLength(1)
      expect(thinkingTraces.value[0].content).toBe('analyzing query')
    })

    it('route.decided → 替换 currentRoute（取最近一次）', () => {
      const { currentRoute, onEvent } = useBusinessEvents()
      onEvent(makeRouteEvent(makeRouteDecision({ intent: 'rag' })))
      expect(currentRoute.value?.intent).toBe('rag')
      onEvent(makeRouteEvent(makeRouteDecision({ intent: 'database' })))
      expect(currentRoute.value?.intent).toBe('database')
    })

    it('未知 type → 静默忽略，不抛错', () => {
      const { onEvent } = useBusinessEvents()
      expect(() =>
        onEvent({ type: 'unknown.event', foo: 'bar' } as unknown as never),
      ).not.toThrow()
    })
  })

  describe('reset', () => {
    it('重置后所有 ref 回到初始状态', () => {
      const { ragCitations, chartMetadata, thinkingTraces, currentRoute, onEvent, reset } =
        useBusinessEvents()
      onEvent(makeRagEvent())
      onEvent(makeChartEvent())
      onEvent(makeThinkingEvent())
      onEvent(makeRouteEvent(makeRouteDecision()))

      expect(ragCitations.value).toHaveLength(1)
      expect(chartMetadata.value).toHaveLength(1)
      expect(thinkingTraces.value).toHaveLength(1)
      expect(currentRoute.value).not.toBeNull()

      reset()

      expect(ragCitations.value).toHaveLength(0)
      expect(chartMetadata.value).toHaveLength(0)
      expect(thinkingTraces.value).toHaveLength(0)
      expect(currentRoute.value).toBeNull()
    })
  })

  describe('多事件混合', () => {
    it('同 run 多次 RAG 引用全部累加；路由决策被替换', () => {
      const { ragCitations, currentRoute, chartMetadata, thinkingTraces, onEvent } =
        useBusinessEvents()

      // 模拟一次完整 run：路由 → 思考 → 多次引用 → 图表
      onEvent(makeRouteEvent(makeRouteDecision()))
      onEvent(makeThinkingEvent({ step: 1 }))
      onEvent(makeRagEvent())
      onEvent(makeRagEvent({ ts: '2026-07-23T12:00:01Z' }))
      onEvent(makeChartEvent())

      expect(ragCitations.value).toHaveLength(2)
      expect(chartMetadata.value).toHaveLength(1)
      expect(thinkingTraces.value).toHaveLength(1)
      expect(currentRoute.value?.intent).toBe('rag')
    })
  })
})
