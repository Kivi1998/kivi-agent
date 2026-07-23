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

/** 路由决策事件（扩展点，gateway 透传 Router 输出时构造；事件总线未冻结） */
export interface RouteDecidedEvent {
  type: 'route.decided'
  run_id: string
  decision: RouteDecision
  ts: string
}

export type BusinessEvent =
  | LlmThinkingEvent
  | ChartRenderedEvent
  | RagSourcesCitedEvent
  | FrontendToolCallRequested
  | FrontendToolCallResponded
  | RunCancelledEvent
  | RouteDecidedEvent

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

// ---- Trace Dashboard 类型（Wave 5.1 WT-G4；与 gateway/dashboard.py 对齐）----

/** 全局汇总（GET /dashboard/summary） */
export interface Summary {
  case_count: number
  success_rate: number
  avg_latency_s: number
  total_tokens: number
  total_cost_usd: number
}

/** Run 摘要（GET /dashboard/runs） */
export interface RunSummary {
  run_id: string
  started_at: string | null
  case_count: number
  success_count: number
}

/** 单 case 评测结果（嵌套在 RunDetail.results 中） */
export interface CaseEvalResult {
  case_id: string
  success: boolean
  latency_s?: number
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
  final_answer?: string
  tool_calls?: Array<{ tool_name: string; success: boolean }>
  rag_sources?: Array<Record<string, unknown>>
}

/** Run 详情（GET /dashboard/runs/:runId） */
export interface RunDetail {
  run_id: string
  case_count: number
  success_count: number
  results: CaseEvalResult[]
}

/** 7 指标（与 metrics_report.py 一致） */
export interface MetricsReport {
  dataset_name: string
  case_count: number
  generated_at: string
  metrics: {
    task_success_rate: { rate: number; passed: number; total: number }
    route_accuracy: { rate: number; matched: number; applicable: number }
    tool_selection_accuracy: {
      exact_match_rate: number
      contain_match_rate: number
      applicable: number
    }
    rag_citation_accuracy: { rate: number; matched: number; applicable: number }
    avg_latency_seconds: {
      avg_s: number
      p50_s: number
      p95_s: number
      count: number
    }
    total_tokens: {
      input: number
      output: number
      cache_read: number
      total: number
    }
    total_cost_usd: { total_usd: number; model: string; per_case_avg_usd: number }
  }
}

/** 单 case 事件流（GET /dashboard/runs/:runId/traces?case_id=...） */
export interface TraceTimeline {
  case_id: string
  events: Array<{
    type: string
    ts: string
    data: Record<string, unknown>
  }>
  tool_calls: Array<{
    tool_name: string
    started_at: string
    finished_at: string | null
    success: boolean
  }>
  rag_sources: Array<Record<string, unknown>>
}

/** 事件流响应（GET /dashboard/runs/:runId/traces） */
export interface TracesResponse {
  run_id: string
  traces: TraceTimeline[]
}
