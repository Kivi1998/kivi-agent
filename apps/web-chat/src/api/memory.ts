// memory dashboard REST API 客户端
//
// 与后端 gateway/memory_dashboard.py 7 端点对齐（agent: package-memory-dashboard-w61）
// 全部请求通过 fetch 发送，base URL 与 dashboard API 一致（/api）
//
// 类型字段命名与后端 Pydantic 模型保持 snake_case；
// 前端 UI 组件可按需映射到 camelCase（不在本层做转换，避免契约失真）

import type {
  MemoryAuditResponse,
  MemoryItem,
  MemoryItemResponse,
  MemoryListResponse,
  MemorySearchResponse,
  MemoryStatus,
  MemoryType
} from '@/types/api'

/** 客户端可注入的 fetch 实现（默认用全局 fetch） */
export type MemoryFetchLike = (
  input: string,
  init?: RequestInit
) => Promise<Response>

/** API 客户端配置（base URL + fetch 实现） */
export interface MemoryDashboardApiOptions {
  baseUrl?: string
  fetchImpl?: MemoryFetchLike
}

/** listMemoryItems 过滤参数 */
export interface MemoryListFilter {
  status?: MemoryStatus
  memory_type?: MemoryType
  source?: string
  limit?: number
  offset?: number
}

/** createMemoryItem 请求体（id/created_at 由后端生成） */
export interface CreateMemoryItemRequest {
  content: string
  memory_type: MemoryType
  importance?: number
  status?: MemoryStatus
  source?: string
  expires_at?: string | null
}

/** updateMemoryItem 请求体（部分更新） */
export interface UpdateMemoryItemRequest {
  content?: string
  memory_type?: MemoryType
  importance?: number
  status?: MemoryStatus
  source?: string
  expires_at?: string | null
}

const DEFAULT_BASE_URL = '/api'

/** 创建 Memory Dashboard API 客户端 */
export function createMemoryDashboardApi(
  options: MemoryDashboardApiOptions = {}
) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL
  const fetchImpl: MemoryFetchLike =
    options.fetchImpl ?? fetch.bind(globalThis)

  /** 解析 JSON 响应，非 2xx 抛出错误 */
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(
        `memory dashboard api error: ${res.status} ${res.statusText} ${text}`
      )
    }
    return (await res.json()) as T
  }

  /** 列出记忆（按 status / memory_type / source 过滤 + limit/offset 分页） */
  function listMemoryItems(
    filter: MemoryListFilter = {}
  ): Promise<MemoryListResponse> {
    const qs = new URLSearchParams()
    if (filter.status) qs.set('status', filter.status)
    if (filter.memory_type) qs.set('memory_type', filter.memory_type)
    if (filter.source) qs.set('source', filter.source)
    if (filter.limit !== undefined) qs.set('limit', String(filter.limit))
    if (filter.offset !== undefined) qs.set('offset', String(filter.offset))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return request<MemoryListResponse>(`/memory/items${suffix}`, {
      method: 'GET'
    })
  }

  /** 单条记忆详情 */
  function getMemoryItem(id: string): Promise<MemoryItemResponse> {
    return request<MemoryItemResponse>(
      `/memory/items/${encodeURIComponent(id)}`,
      { method: 'GET' }
    )
  }

  /** 手动创建一条记忆 */
  function createMemoryItem(
    body: CreateMemoryItemRequest
  ): Promise<MemoryItemResponse> {
    return request<MemoryItemResponse>(`/memory/items`, {
      method: 'POST',
      body: JSON.stringify(body)
    })
  }

  /** 部分更新记忆（content / type / importance / status / expires_at） */
  function updateMemoryItem(
    id: string,
    body: UpdateMemoryItemRequest
  ): Promise<MemoryItemResponse> {
    return request<MemoryItemResponse>(
      `/memory/items/${encodeURIComponent(id)}`,
      { method: 'PATCH', body: JSON.stringify(body) }
    )
  }

  /** 删除记忆（硬删） */
  function deleteMemoryItem(id: string): Promise<{ deleted: boolean }> {
    return request<{ deleted: boolean }>(
      `/memory/items/${encodeURIComponent(id)}`,
      { method: 'DELETE' }
    )
  }

  /** 归档记忆（status=archived） */
  function archiveMemoryItem(id: string): Promise<MemoryItemResponse> {
    return request<MemoryItemResponse>(
      `/memory/items/${encodeURIComponent(id)}/archive`,
      { method: 'POST' }
    )
  }

  /** 向量检索（q + top_k） */
  function searchMemory(
    query: string,
    topK: number = 5
  ): Promise<MemorySearchResponse> {
    const qs = new URLSearchParams({ q: query, top_k: String(topK) })
    return request<MemorySearchResponse>(`/memory/search?${qs.toString()}`, {
      method: 'GET'
    })
  }

  /** 单条记忆的审计历史 */
  function getMemoryAudit(
    memoryId: string
  ): Promise<MemoryAuditResponse> {
    return request<MemoryAuditResponse>(
      `/memory/audit?memory_id=${encodeURIComponent(memoryId)}`,
      { method: 'GET' }
    )
  }

  return {
    listMemoryItems,
    getMemoryItem,
    createMemoryItem,
    updateMemoryItem,
    deleteMemoryItem,
    archiveMemoryItem,
    searchMemory,
    getMemoryAudit,
    request
  }
}

export type MemoryDashboardApi = ReturnType<typeof createMemoryDashboardApi>

/** 内部 helper：把 importance 0-1 渲染成百分比 */
export function formatImportance(value: number | undefined | null): string {
  if (value === undefined || value === null) return '—'
  return (value * 100).toFixed(1) + '%'
}

/** 内部 helper：把记忆类型映射到中文标签（供 UI 显示用） */
export const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  user: '用户',
  feedback: '反馈',
  project: '项目',
  reference: '参考',
  task: '任务'
}

/** 内部 helper：记忆状态映射到中文标签 */
export const MEMORY_STATUS_LABELS: Record<MemoryStatus, string> = {
  active: '活跃',
  pending: '待处理',
  archived: '已归档',
  expired: '已过期'
}

/** 内部 helper：从 MemoryItem[] 算一次简单汇总（active / total） */
export function computeMemorySummary(items: MemoryItem[]): {
  total: number
  active: number
  archived: number
  avg_importance: number
} {
  const total = items.length
  const active = items.filter((i) => i.status === 'active').length
  const archived = items.filter((i) => i.status === 'archived').length
  const avgImportance =
    total > 0
      ? items.reduce((acc, i) => acc + i.importance, 0) / total
      : 0
  return { total, active, archived, avg_importance: avgImportance }
}
