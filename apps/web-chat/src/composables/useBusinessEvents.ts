import { ref } from 'vue'
import type { Ref } from 'vue'

/**
 * Web 端业务事件类型定义（co-located in composable）。
 *
 * **为什么不在 types/api.ts**：WT-E2 在 `src/types/api.ts` 写完整的 WS 协议类型；
 * WT-E3 的硬约束是"仅在 components/ + composables/ 下新增文件"，因此
 * 4 个业务事件相关类型暂时在 composable 中定义并 export，WT-E2 完成 types/api.ts
 * 后由主控集成期做迁移（import 路径替换为 '../types/api'）。
 *
 * 类型来源（与 v1 §5.2.1 Pydantic 一一对应）：
 *   - RagSourcesCitedEvent / ChartRenderedEvent / LlmThinkingEvent → src/kivi_agent/core/bus/events.py
 *   - RouteDecision → src/kivi_agent/core/agents/business_router.py
 *   - route.decided 是 gateway 透传 Router 输出时构造的事件（不在 Event 联合里，扩展点）
 */

export interface RagSource {
  id?: string
  title?: string
  score?: number
  url?: string
  [key: string]: unknown
}

export interface RagSourcesCitedEvent {
  type: 'rag.sources_cited'
  run_id: string
  sources: RagSource[]
  ts: string
}

export interface ChartRenderedEvent {
  type: 'chart.rendered'
  run_id: string
  chart_id: string
  option_dict: Record<string, unknown>
  ts: string
}

export interface LlmThinkingEvent {
  type: 'llm.thinking'
  run_id: string
  step: number
  content: string
  ts: string
}

export type BusinessIntent = 'rag' | 'web_search' | 'database' | 'general' | 'synthesizer'

export interface RouteDecision {
  query: string
  intent: BusinessIntent
  target_profiles: string[]
  is_multi_intent: boolean
  confidence: number
  matched_keywords: string[]
}

export interface RouteDecidedEvent {
  type: 'route.decided'
  run_id: string
  decision: RouteDecision
  ts: string
}

/** WebSocket 推过来的所有事件形状（type 字段是判别字段） */
export type BusinessEvent =
  | RagSourcesCitedEvent
  | ChartRenderedEvent
  | LlmThinkingEvent
  | RouteDecidedEvent

export interface UseBusinessEventsReturn {
  ragCitations: Ref<RagSourcesCitedEvent[]>
  chartMetadata: Ref<ChartRenderedEvent[]>
  thinkingTraces: Ref<LlmThinkingEvent[]>
  currentRoute: Ref<RouteDecision | null>
  onEvent: (event: BusinessEvent | { type: string; [k: string]: unknown }) => void
  reset: () => void
}

/**
 * useBusinessEvents — 路由 6 类业务事件到响应式状态。
 *
 * 设计要点：
 * - 单一事件入口 `onEvent(event)`：消费方（ws.ts）只需要把每个 event 推过来
 * - 累加型 vs 替换型：citations / charts / thinking 是累加（多 run 序列），
 *   currentRoute 是替换（最近一次路由决策）
 * - 未知 type 静默忽略：保证后续新增事件不会让本 composable 崩溃
 */
export function useBusinessEvents(): UseBusinessEventsReturn {
  const ragCitations = ref<RagSourcesCitedEvent[]>([])
  const chartMetadata = ref<ChartRenderedEvent[]>([])
  const thinkingTraces = ref<LlmThinkingEvent[]>([])
  const currentRoute = ref<RouteDecision | null>(null)

  function onEvent(event: BusinessEvent | { type: string; [k: string]: unknown }): void {
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
