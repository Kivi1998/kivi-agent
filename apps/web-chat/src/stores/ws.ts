// WS Pinia store：WebSocket 连接状态

import { defineStore } from 'pinia'
import { ref } from 'vue'

/** WebSocket 状态机（与 WT-E4 状态机对齐） */
export type WsConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'error'

export const useWsStore = defineStore('ws', () => {
  // ---- state ----
  const state = ref<WsConnectionState>('idle')
  const sessionId = ref<string | null>(null)
  const lastError = ref<string | null>(null)
  const lastEventAt = ref<string | null>(null)
  const reconnectAttempts = ref(0)

  // ---- actions ----

  /** 进入 connecting 状态 */
  function setConnecting(sid: string): void {
    state.value = 'connecting'
    sessionId.value = sid
    lastError.value = null
  }

  /** 进入 open 状态 */
  function setOpen(): void {
    state.value = 'open'
    reconnectAttempts.value = 0
    lastError.value = null
  }

  /** 进入 reconnecting 状态 */
  function setReconnecting(): void {
    state.value = 'reconnecting'
    reconnectAttempts.value += 1
  }

  /** 进入 error 状态 */
  function setError(message: string): void {
    state.value = 'error'
    lastError.value = message
  }

  /** 进入 closed 状态 */
  function setClosed(): void {
    state.value = 'closed'
  }

  /** 重置为 idle */
  function reset(): void {
    state.value = 'idle'
    sessionId.value = null
    lastError.value = null
    reconnectAttempts.value = 0
  }

  /** 记录最近一次事件时间 */
  function markEvent(ts: string): void {
    lastEventAt.value = ts
  }

  return {
    state,
    sessionId,
    lastError,
    lastEventAt,
    reconnectAttempts,
    setConnecting,
    setOpen,
    setReconnecting,
    setError,
    setClosed,
    reset,
    markEvent
  }
})
