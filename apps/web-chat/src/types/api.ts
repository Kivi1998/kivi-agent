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

/** 前端地图加载完成（与 MapGeojsonLoadedEvent 对齐；Wave 7 demo 4 新增） */
export interface MapGeojsonLoadedEvent {
  type: 'map.geojson_loaded'
  url: string
  layer_id: string
  features_count: number
  bbox: [number, number, number, number] | null
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
  | MapGeojsonLoadedEvent

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

// ---- T11 多 Agent 协作 Dashboard 类型（Wave 5.2 WT-H4；与 gateway/team_dashboard.py 对齐）----

/** 团队全局汇总（GET /api/team/summary） */
export interface TeamSummary {
  team_count: number
  success_rate: number
  avg_delegation_accuracy: number
  avg_handoff_quality: number
  avg_coordination_latency_s: number
  avg_agent_utilization: number
}

/** 团队运行摘要（GET /api/team/teams） */
export interface TeamSummaryItem {
  team_id: string
  goal: string
  member_count: number
  success: boolean
  created_at: string | null
  finished_at: string | null
}

/** 团队列表响应（GET /api/team/teams） */
export interface TeamListResponse {
  total: number
  teams: TeamSummaryItem[]
}

/** 成员最终结果（嵌套在 TeamDetail.member_outcomes 中） */
export interface MemberOutcome {
  member_id: string
  role: string
  success: boolean
  steps: number
  tool_calls: number
  finished_at: string | null
  final_answer: string
}

/** 团队详情（GET /api/team/teams/:teamId） */
export interface TeamDetail {
  team_id: string
  goal: string
  member_count: number
  success: boolean
  created_at: string | null
  finished_at: string | null
  member_outcomes: MemberOutcome[]
}

/** 委派步骤（GET /api/team/teams/:teamId/delegations） */
export interface DelegationStep {
  step_id: string
  from_member: string
  to_member: string
  sub_task: string
  message: string
  success: boolean
  ts: string
}

/** T11 6 指标（GET /api/team/teams/:teamId/metrics） */
export interface T11Metrics {
  team_success_rate: { rate: number; passed: number; total: number }
  delegation_accuracy: { rate: number; matched: number; applicable: number }
  handoff_quality: { rate: number; successful: number; total: number }
  coordination_latency_s: { avg_s: number; p50_s: number; p95_s: number; count: number }
  agent_utilization: { rate: number; tool_calls: number; total_steps: number }
  role_consistency: { rate: number; role_changes: number; total_steps: number }
}

// ---- T12 coding Agent Dashboard 类型（Wave 5.2 WT-H4；与 gateway/coding_dashboard.py 对齐）----

/** coding 全局汇总（GET /api/coding/summary） */
export interface CodingSummary {
  run_count: number
  task_completion_rate: number
  tests_passed_rate: number
  avg_iteration_count: number
  avg_time_to_first_pass_s: number
  self_recovery_rate: number
}

/** coding run 摘要（GET /api/coding/runs） */
export interface CodingRunItem {
  run_id: string
  task: string
  test_file: string
  iteration_count: number
  success: boolean
  started_at: string | null
  finished_at: string | null
}

/** coding run 列表响应（GET /api/coding/runs） */
export interface CodingRunListResponse {
  total: number
  runs: CodingRunItem[]
}

/** Patch 记录（GET /api/coding/runs/:runId/patches） */
export interface PatchRecord {
  patch_id: string
  iteration: number
  file_path: string
  hunks_proposed: number
  hunks_applied: number
  diff: string
  ts: string
}

/** 单次 pytest 记录（GET /api/coding/runs/:runId/patches 内嵌） */
export interface TestRunRecord {
  iteration: number
  tests_total: number
  tests_passed: number
  tests_failed: number
  compile_passed: boolean
  raw_output: string
  ts: string
}

/** coding run 详情（GET /api/coding/runs/:runId） */
export interface CodingDetail {
  run_id: string
  task: string
  test_file: string
  iteration_count: number
  success: boolean
  started_at: string | null
  finished_at: string | null
  patches: PatchRecord[]
  test_runs: TestRunRecord[]
}

/** T12 8 指标（GET /api/coding/runs/:runId/metrics） */
export interface T12Metrics {
  task_completion_rate: { rate: number; passed: number; total: number }
  tests_passed_rate: { rate: number; passed: number; total: number }
  patch_quality: { rate: number; hunks_applied: number; hunks_proposed: number }
  iteration_count: { value: number; iterations: number }
  time_to_first_pass_s: { avg_s: number; first_pass_iterations: number }
  self_recovery_rate: { rate: number; auto_recovered: number; total_failures: number }
  compile_success_rate: { rate: number; compile_passed: number; total_runs: number }
  test_growth_rate: { rate: number; tests_added: number; iterations: number }
}

// ---- Wave 6.1 WT-J4: 前端记忆管理 UI 类型（与 gateway/memory_dashboard.py 对齐）----

/** 记忆类型：与 src/kivi_agent/core/memory/types.py 的 MemoryType Literal 对齐 */
export type MemoryType = 'user' | 'feedback' | 'project' | 'reference' | 'task'

/** 记忆状态：与 MemoryItem.status 对齐 */
export type MemoryStatus = 'active' | 'pending' | 'archived' | 'expired'

/** 记忆审计事件类型 */
export type MemoryAuditAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'archive'
  | 'expire'
  | 'dedup_merge'
  | 'read'

/** 单条记忆（与 MemoryItem Pydantic 对齐） */
export interface MemoryItem {
  id: string
  content: string
  memory_type: MemoryType
  importance: number
  status: MemoryStatus
  source: string
  created_at: string
  expires_at: string | null
  updated_at: string | null
}

/** GET /api/memory/items 单条响应（带 metadata） */
export interface MemoryItemResponse {
  item: MemoryItem
}

/** GET /api/memory/items 列表响应（带分页 total） */
export interface MemoryListResponse {
  total: number
  items: MemoryItem[]
}

/** 搜索命中结果（带 score 字段） */
export interface MemorySearchResult {
  id: string
  content: string
  score: number
  memory_type: MemoryType
  importance: number
  status: MemoryStatus
  source: string
  created_at: string
}

/** GET /api/memory/search 响应 */
export interface MemorySearchResponse {
  query: string
  top_k: number
  results: MemorySearchResult[]
}

/** 记忆审计事件 */
export interface MemoryAuditEvent {
  event_id: string
  memory_id: string
  action: MemoryAuditAction
  actor: string
  ts: string
  detail: Record<string, unknown>
}

/** GET /api/memory/audit 响应 */
export interface MemoryAuditResponse {
  memory_id: string
  events: MemoryAuditEvent[]
}
