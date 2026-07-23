// WebSocket 客户端（基础版，重连逻辑由 WT-E4 处理）

import type { BusinessEvent } from '@/types/api'

/** 业务事件回调签名 */
export type BusinessEventHandler = (event: BusinessEvent | Record<string, unknown>) => void

/** WebSocket 构造器（可注入 fake，签名匹配 DOM lib） */
export interface WebSocketCtor {
  new (url: string, protocols?: string | string[]): WebSocket
}

/** WebSocket 客户端配置 */
export interface WebSocketOptions {
  baseUrl?: string
  protocols?: string | string[]
  WebSocketImpl?: WebSocketCtor
  onEvent: BusinessEventHandler
}

const DEFAULT_WS_BASE = ''

/** 创建 WebSocket 连接，返回 WebSocket 实例 */
export function connectWebSocket(
  sessionId: string,
  options: WebSocketOptions
): WebSocket {
  const baseUrl = options.baseUrl ?? DEFAULT_WS_BASE
  const Ctor: WebSocketCtor =
    options.WebSocketImpl ??
    (typeof WebSocket !== 'undefined'
      ? (WebSocket as unknown as WebSocketCtor)
      : ((): WebSocket => {
          throw new Error('WebSocket is not available in this environment')
        }) as unknown as WebSocketCtor)

  const url = `${baseUrl}/sessions/${encodeURIComponent(sessionId)}/ws`
  const ws = new Ctor(url, options.protocols)

  ws.addEventListener('message', (ev: MessageEvent<string | ArrayBuffer>) => {
    const raw = typeof ev.data === 'string' ? ev.data : ''
    if (!raw) return
    try {
      const parsed: unknown = JSON.parse(raw)
      options.onEvent(parsed as BusinessEvent)
    } catch {
      // 非 JSON 数据当作原始负载透传
      options.onEvent({ type: 'ws.raw', data: raw } as unknown as BusinessEvent)
    }
  })

  return ws
}
