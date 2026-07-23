import { ref } from 'vue'
import type { Ref } from 'vue'

import type {
  BusinessEvent,
  ChartRenderedEvent,
  LlmThinkingEvent,
  RagSourcesCitedEvent,
  RouteDecidedEvent,
  RouteDecision,
} from '../types/api'

/**
 * useBusinessEvents — 路由 6 类业务事件到响应式状态。
 *
 * 类型来源：与后端 v1 §5.2.1 6 业务事件一一对齐（`src/kivi_agent/core/bus/events.py`）。
 * 设计要点：
 * - 单一事件入口 `onEvent(event)`：消费方（ws.ts）只需要把每个 event 推过来
 * - 累加型 vs 替换型：citations / charts / thinking 是累加（多 run 序列），
 *   currentRoute 是替换（最近一次路由决策）
 * - 未知 type 静默忽略：保证后续新增事件不会让本 composable 崩溃
 */
export interface UseBusinessEventsReturn {
  ragCitations: Ref<RagSourcesCitedEvent[]>
  chartMetadata: Ref<ChartRenderedEvent[]>
  thinkingTraces: Ref<LlmThinkingEvent[]>
  currentRoute: Ref<RouteDecision | null>
  onEvent: (event: BusinessEvent | { type: string }) => void
  reset: () => void
}

export function useBusinessEvents(): UseBusinessEventsReturn {
  const ragCitations = ref<RagSourcesCitedEvent[]>([])
  const chartMetadata = ref<ChartRenderedEvent[]>([])
  const thinkingTraces = ref<LlmThinkingEvent[]>([])
  const currentRoute = ref<RouteDecision | null>(null)

  function onEvent(event: BusinessEvent | { type: string }): void {
    switch (event.type) {
      case 'rag.sources_cited':
        ragCitations.value.push(event as RagSourcesCitedEvent)
        break
      case 'chart.rendered':
        chartMetadata.value.push(event as ChartRenderedEvent)
        break
      case 'llm.thinking':
        thinkingTraces.value.push(event as LlmThinkingEvent)
        break
      case 'route.decided':
        // event.decision 由 gateway 注入（来自 Router.route(query) 的输出）
        currentRoute.value = (event as RouteDecidedEvent).decision
        break
      default:
        // 未知事件类型：不报错，保持前向兼容
        break
    }
  }

  function reset(): void {
    ragCitations.value = []
    chartMetadata.value = []
    thinkingTraces.value = []
    currentRoute.value = null
  }

  return {
    ragCitations,
    chartMetadata,
    thinkingTraces,
    currentRoute,
    onEvent,
    reset,
  }
}
