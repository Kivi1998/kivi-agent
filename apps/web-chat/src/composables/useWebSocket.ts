// useWebSocket：WebSocket 状态机 + 心跳 + 指数退避重连
//
// 5 个状态：connecting / open / reconnecting / closed / error
// 心跳：每 10s 发 ping，30s 没收到 pong 主动断线触发重连
// 重连：指数退避（1s / 2s / 4s / 8s / 16s / 30s max）
//
// 与 `apps/web-chat/src/api/ws.ts` 的 `connectWebSocket` 配套使用：
// - 业务事件经 onEvent 回调抛出（ping/pong 内部消化）
// - `close()` 主动关闭，状态切到 closed（不会自动重连）
// - 组件 onUnmounted 时自动 close，避免内存泄漏
//
// 测试通过可选 `WebSocketImpl` / `setTimeout` / `clearInterval` 注入实现。

import { onUnmounted, ref } from 'vue'

/** WebSocket 状态机 */
export type WSState =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error'

/** 业务事件回调签名（与 api/ws.ts 保持一致） */
export type WSMessageHandler = (event: unknown) => void

/** 可注入的 WebSocket 构造器（用于测试） */
export interface WebSocketFactory {
  new (url: string, protocols?: string | string[]): WebSocket
}

/** useWebSocket 配置 */
export interface UseWebSocketOptions {
  /** 业务事件回调（ping/pong 已被内部消化） */
  onEvent: WSMessageHandler
  /** WebSocket 构造器（默认全局 WebSocket；测试可注入 fake） */
  WebSocketImpl?: WebSocketFactory
  /** 心跳间隔（ms，默认 10000） */
  heartbeatInterval?: number
  /** 心跳超时（ms，lastPong 距今超过此值主动关闭，默认 30000） */
  heartbeatTimeout?: number
  /** 最大重连退避（ms，默认 30000） */
  maxReconnectDelay?: number
  /** 初始重连退避（ms，默认 1000） */
  initialReconnectDelay?: number
  /** 状态或事件变化时的错误回调（用于 useErrorHandler 上报） */
  onError?: (message: string) => void
  /** 重连尝试次数回调（用于 useErrorHandler 提示） */
  onReconnectAttempt?: (attempts: number) => void
}

const DEFAULTS = {
  heartbeatInterval: 10_000,
  heartbeatTimeout: 30_000,
  maxReconnectDelay: 30_000,
  initialReconnectDelay: 1_000
}

/**
 * 创建 WebSocket 状态机 composable。
 *
 * 用法：
 *   const { state, reconnectAttempts, connect, close } = useWebSocket({
 *     sessionId: 'abc',
 *     onEvent: (e) => { ... }
 *   })
 *   onMounted(connect)
 */
export function useWebSocket(
  sessionId: string,
  options: UseWebSocketOptions
) {
  const {
    onEvent,
    WebSocketImpl,
    heartbeatInterval = DEFAULTS.heartbeatInterval,
    heartbeatTimeout = DEFAULTS.heartbeatTimeout,
    maxReconnectDelay = DEFAULTS.maxReconnectDelay,
    initialReconnectDelay = DEFAULTS.initialReconnectDelay,
    onError,
    onReconnectAttempt
  } = options

  const state = ref<WSState>('connecting')
  const reconnectAttempts = ref(0)
  const lastPongAt = ref<number | null>(null)

  let ws: WebSocket | null = null
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  // 主动关闭标志：onclose 时检查，避免自动重连
  let isManualClose = false
  // 已卸载标志：卸载后不再派发事件
  let isDisposed = false

  function buildUrl(): string {
    // 默认通过 Vite proxy 转发到 Gateway（http://host:port → ws 同源）
    const proto = typeof location !== 'undefined' && location.protocol === 'https:' ? 'wss' : 'ws'
    const host = typeof location !== 'undefined' ? location.host : 'localhost:5173'
    return `${proto}://${host}/sessions/${encodeURIComponent(sessionId)}/ws`
  }

  function clearTimers(): void {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function startHeartbeat(): void {
    if (heartbeatTimer !== null) return
    heartbeatTimer = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      // 超时未收到 pong，主动关闭触发 onclose → scheduleReconnect
      if (
        lastPongAt.value !== null &&
        Date.now() - lastPongAt.value > heartbeatTimeout
      ) {
        try {
          ws.close()
        } catch {
          // ignore
        }
        return
      }
      try {
        ws.send(JSON.stringify({ type: 'ping' }))
      } catch {
        // send 失败通常意味着 socket 已断，下一 tick 的 readyState 检查会处理
      }
    }, heartbeatInterval)
  }

  function scheduleReconnect(): void {
    if (isManualClose || isDisposed) return
    state.value = 'reconnecting'
    const attempts = reconnectAttempts.value
    const delay = Math.min(
      initialReconnectDelay * 2 ** attempts,
      maxReconnectDelay
    )
    reconnectAttempts.value = attempts + 1
    if (onReconnectAttempt) onReconnectAttempt(reconnectAttempts.value)
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      connect()
    }, delay)
  }

  function connect(): void {
    if (isDisposed) return
    if (isManualClose) return
    isManualClose = false
    state.value = 'connecting'
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    const Ctor: WebSocketFactory =
      WebSocketImpl ??
      (typeof WebSocket !== 'undefined'
        ? (WebSocket as unknown as WebSocketFactory)
        : ({
            new (): never {
              throw new Error('WebSocket is not available in this environment')
            }
          } as unknown as WebSocketFactory))

    const url = buildUrl()
    try {
      ws = new Ctor(url)
    } catch (e) {
      // 构造失败 → error 状态 + 调度重连
      const msg = e instanceof Error ? e.message : String(e)
      state.value = 'error'
      if (onError) onError(`ws construct failed: ${msg}`)
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      if (isDisposed) return
      state.value = 'open'
      reconnectAttempts.value = 0
      lastPongAt.value = Date.now()
      startHeartbeat()
    }

    ws.onmessage = (e: MessageEvent) => {
      if (isDisposed) return
      const raw = typeof e.data === 'string' ? e.data : ''
      if (!raw) return
      let event: unknown
      try {
        event = JSON.parse(raw)
      } catch {
        // 非 JSON 透传为原始负载
        event = { type: 'ws.raw', data: raw }
      }
      // pong 仅用于心跳；不派发给业务回调
      if (
        event !== null &&
        typeof event === 'object' &&
        (event as { type?: unknown }).type === 'pong'
      ) {
        lastPongAt.value = Date.now()
        return
      }
      onEvent(event)
    }

    ws.onclose = () => {
      if (heartbeatTimer !== null) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
      if (isDisposed) return
      if (isManualClose) {
        state.value = 'closed'
        return
      }
      scheduleReconnect()
    }

    ws.onerror = () => {
      if (isDisposed) return
      state.value = 'error'
      if (onError) onError('ws onerror fired')
      // onclose 会在 onerror 之后触发，由 onclose 调度重连
    }
  }

  /** 主动关闭：进入 closed 状态，不再自动重连 */
  function close(): void {
    isManualClose = true
    clearTimers()
    if (ws) {
      try {
        ws.close()
      } catch {
        // ignore
      }
    }
    state.value = 'closed'
  }

  /** 强制重置状态机：清空重连计数，重新建立连接 */
  function reset(): void {
    isManualClose = false
    reconnectAttempts.value = 0
    if (ws) {
      try {
        ws.close()
      } catch {
        // ignore
      }
    }
    clearTimers()
    connect()
  }

  onUnmounted(() => {
    isDisposed = true
    close()
  })

  return {
    state,
    reconnectAttempts,
    lastPongAt,
    connect,
    close,
    reset
  }
}
