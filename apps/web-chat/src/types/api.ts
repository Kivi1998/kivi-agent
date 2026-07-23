// TypeScript 类型，与后端 Pydantic 模型一一对齐
// 见 src/kivi_agent/gateway/main.py 与 src/kivi_agent/core/bus/events.py

// ---- 基础枚举 ----

export type SessionStatus = 'active' | 'waiting_for_input' | 'closed'

export type Intent = 'rag' | 'web_search' | 'database' | 'general' | 'synthesizer'

// ---- HTTP API 模型（与 gateway/main.py 对齐）----

/** POST /sessions 请求体（与 StartSessionRequest 对齐） */
export interface StartSessionRequest {
  user_id: string
  goal: string
}

/** Session 元数据响应（与 SessionInfoResponse 对齐） */
export interface SessionInfo {
  session_id: string
  user_id: string
  goal: string
  created_at: string
  status: SessionStatus | string
  run_id: string | null
}

/** GET /sessions 响应（与 SessionListResponse 对齐） */
export interface SessionListResponse {
  user_id: string
  sessions: SessionInfo[]
}

/** POST /sessions/{id}/cancel 请求体（与 CancelRequest 对齐） */
export interface CancelRequest {
  reason: string
}

/** POST /sessions/{id}/cancel 响应（与 CancelResponse 对齐） */
export interface CancelResponse {
  cancelled: boolean
  session_id: string
  ts: string
}

// ---- 业务事件（与 core/bus/events.py v1 §5.2.1 6 事件对齐）----

/** 推理内容（与 LlmThinkingEvent 对齐） */
export interface LlmThinkingEvent {
  type: 'llm.thinking'
  run_id: string
  step: number
  content: string
  ts: string
}

/** 图表元数据（与 ChartRenderedEvent 对齐） */
export interface ChartRenderedEvent {
  type: 'chart.rendered'
  run_id: string
  chart_id: string
  option_dict: Record<string, unknown>
  ts: string
}

/** RAG 引用列表（与 RagSourcesCitedEvent 对齐） */
export interface RagSource {
  id?: string
  title?: string
  score?: number
  url?: string
}
export interface RagSourcesCitedEvent {
  type: 'rag.sources_cited'
  run_id: string
  sources: RagSource[]
  ts: string
}

/** 前端工具调用请求（与 FrontendToolCallRequested 对齐） */
export interface FrontendToolCallRequested {
  type: 'frontend.tool_call_requested'
  run_id: string
  request_id: string
  tool_name: string
  args: Record<string, unknown>
  ts: string
}

/** 前端工具调用响应（与 FrontendToolCallResponded 对齐） */
export interface FrontendToolCallResponded {
  type: 'frontend.tool_call_responded'
  run_id: string
  request_id: string
  result: Record<string, unknown>
  ts: string
}

/** Run 取消（与 RunCancelledEvent 对齐） */
export interface RunCancelledEvent {
  type: 'run.cancelled'
  run_id: string
  reason: string
  ts: string
}

// ---- 业务事件联合（v1 §5.2.1 冻结的 6 类）----

export type BusinessEvent =
  | LlmThinkingEvent
  | ChartRenderedEvent
  | RagSourcesCitedEvent
  | FrontendToolCallRequested
  | FrontendToolCallResponded
  | RunCancelledEvent

// ---- 路由决策（v1 §3.1 冻结字段，TypeScript 反推）----

/** 路由决策记录（与 BusinessRouter 输出对齐） */
export interface RouteDecision {
  query: string
  intent: Intent
  target_profiles: string[]
  is_multi_intent: boolean
  confidence: number
  matched_keywords: string[]
}

// ---- 业务事件聚合视图（v1 §5.2.1 多事件按 run_id 聚合）----

/** 业务事件按 run_id 聚合的视图（供 WT-E3 组件使用） */
export interface BusinessEventBundle {
  run_id: string
  thinking: LlmThinkingEvent[]
  charts: ChartRenderedEvent[]
  rag_sources: RagSourcesCitedEvent[]
  frontend_tool_calls: FrontendToolCallRequested[]
  cancelled: RunCancelledEvent | null
}
