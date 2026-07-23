// session REST API 客户端
// 全部请求通过 fetch 发送，base URL 在测试中可被覆写

import type {
  CancelResponse,
  SessionInfo,
  SessionListResponse,
  StartSessionRequest
} from '@/types/api'

/** 客户端可注入的 fetch 实现（默认用全局 fetch） */
export type FetchLike = (
  input: string,
  init?: RequestInit
) => Promise<Response>

/** API 客户端配置（base URL + fetch 实现） */
export interface SessionApiOptions {
  baseUrl?: string
  fetchImpl?: FetchLike
}

const DEFAULT_BASE_URL = '/api'

/** 创建 Session API 客户端 */
export function createSessionApi(options: SessionApiOptions = {}) {
  const baseUrl = options.baseUrl ?? DEFAULT_BASE_URL
  const fetchImpl: FetchLike = options.fetchImpl ?? fetch.bind(globalThis)

  /** 解析 JSON 响应，非 2xx 抛出错误 */
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetchImpl(`${baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init
    })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(
        `session api error: ${res.status} ${res.statusText} ${text}`
      )
    }
    return (await res.json()) as T
  }

  /** 创建并启动 session */
  function startSession(req: StartSessionRequest): Promise<SessionInfo> {
    return request<SessionInfo>('/sessions', {
      method: 'POST',
      body: JSON.stringify(req)
    })
  }

  /** 查询单个 session 元数据 */
  function getSession(sessionId: string): Promise<SessionInfo> {
    return request<SessionInfo>(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'GET'
    })
  }

  /** 列出 user 的所有 session */
  function listSessions(userId: string): Promise<SessionInfo[]> {
    const qs = new URLSearchParams({ user_id: userId })
    return request<SessionListResponse>(`/sessions?${qs.toString()}`, {
      method: 'GET'
    }).then((r) => r.sessions)
  }

  /** 取消运行中的 session */
  function cancelSession(sessionId: string, reason?: string): Promise<CancelResponse> {
    return request<CancelResponse>(
      `/sessions/${encodeURIComponent(sessionId)}/cancel`,
      {
        method: 'POST',
        body: JSON.stringify({ reason: reason ?? '' })
      }
    )
  }

  return { startSession, getSession, listSessions, cancelSession, request }
}

export type SessionApi = ReturnType<typeof createSessionApi>
