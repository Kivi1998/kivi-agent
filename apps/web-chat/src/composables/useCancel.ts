// useCancel：取消 session 的 composable
//
// 调用 `cancel(sessionId, reason)` → POST /sessions/{id}/cancel
// - 状态机：isCancelling（请求中）/ lastError（最近一次错误）
// - 完成后总是复位 isCancelling；不会 throw
//
// 通过 `useCancel({ api })` 注入 SessionApi 客户端便于测试；
// 不传时使用默认工厂（走 Vite proxy → Gateway）。

import { ref } from 'vue'
import { createSessionApi, type SessionApi } from '../api/session'

/** useCancel 配置 */
export interface UseCancelOptions {
  api?: SessionApi
  /** 错误回调（用于 useErrorHandler 上报） */
  onError?: (message: string) => void
}

/**
 * 创建 useCancel composable。
 *
 * 用法：
 *   const { isCancelling, lastError, cancel } = useCancel({ onError })
 *   await cancel('session-id', 'user pressed stop')
 */
export function useCancel(options: UseCancelOptions = {}) {
  const { onError } = options
  // 懒加载 API 客户端，避免 SSR 环境 fetch 未定义
  const api: SessionApi = options.api ?? createSessionApi()

  const isCancelling = ref(false)
  const lastError = ref<string | null>(null)
  /** 最近一次成功取消的 sessionId（用于 UI 反馈） */
  const lastCancelledId = ref<string | null>(null)
  /** 最近一次成功取消的时间戳（ms） */
  const lastCancelledAt = ref<number | null>(null)

  /**
   * 取消指定 session。
   * - 成功：lastError 清空，lastCancelledId 写入
   * - 失败：lastError 写入错误信息，isCancelling 复位
   */
  async function cancel(sessionId: string, reason?: string): Promise<boolean> {
    if (!sessionId) {
      const msg = 'cancel: sessionId is required'
      lastError.value = msg
      if (onError) onError(msg)
      return false
    }
    isCancelling.value = true
    lastError.value = null
    try {
      await api.cancelSession(sessionId, reason)
      lastCancelledId.value = sessionId
      lastCancelledAt.value = Date.now()
      return true
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      lastError.value = msg
      if (onError) onError(msg)
      return false
    } finally {
      isCancelling.value = false
    }
  }

  /** 清除最近一次错误（用户在 UI 上关闭 banner 时调用） */
  function clearError(): void {
    lastError.value = null
  }

  return {
    isCancelling,
    lastError,
    lastCancelledId,
    lastCancelledAt,
    cancel,
    clearError
  }
}
