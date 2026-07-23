// useErrorHandler：统一错误状态机
//
// 3 类错误：
// - API 错误：fetch 失败 / 4xx / 5xx
// - WS 错误：连接失败 / 断线
// - Business 错误：业务事件 type="error" 或 session.status="failed"
//
// 设计：
// - 错误列表只增不删（dismiss/clear 显式清理）
// - 不依赖任何外部 store；可被 useCancel / useWebSocket 回调驱动
// - 暴露 helpers：lastError / hasErrors / dismiss / clear

import { computed, ref } from 'vue'

/** 错误类别 */
export type ErrorCategory = 'api' | 'ws' | 'business'

/** 错误对象 */
export interface AppError {
  /** 错误类别 */
  category: ErrorCategory
  /** 业务/后端错误码（可选） */
  code?: string
  /** 用户可读消息 */
  message: string
  /** 产生时间（ms epoch） */
  ts: number
}

/** 报告错误时的入参 */
export type ReportErrorInput = {
  category: ErrorCategory
  message: string
  code?: string
}

/** useErrorHandler 配置 */
export interface UseErrorHandlerOptions {
  /** 最多保留多少条错误（默认 20；超出 FIFO 淘汰） */
  maxRetained?: number
}

/**
 * 创建 useErrorHandler composable。
 *
 * 用法：
 *   const { errors, hasErrors, lastError, report, dismiss, clear } = useErrorHandler()
 *   useWebSocket({ ..., onError: (msg) => report({ category: 'ws', message: msg }) })
 */
export function useErrorHandler(options: UseErrorHandlerOptions = {}) {
  const { maxRetained = 20 } = options
  const errors = ref<AppError[]>([])

  /**
   * 上报一条错误。
   * - 相同 category + message 5s 内重复会上抛（不重复）以避免刷屏
   * - 超过 maxRetained 会丢弃最早的一条
   */
  function report(input: ReportErrorInput): void {
    const ts = Date.now()
    const last = errors.value[errors.value.length - 1]
    if (
      last &&
      last.category === input.category &&
      last.message === input.message &&
      ts - last.ts < 5_000
    ) {
      return
    }
    const entry: AppError = {
      category: input.category,
      message: input.message,
      ts
    }
    if (input.code !== undefined) {
      entry.code = input.code
    }
    errors.value = [...errors.value, entry]
    // FIFO 淘汰
    if (errors.value.length > maxRetained) {
      errors.value = errors.value.slice(errors.value.length - maxRetained)
    }
  }

  /** 关闭某条错误（按 index） */
  function dismiss(index: number): void {
    if (index < 0 || index >= errors.value.length) return
    const next = errors.value.slice()
    next.splice(index, 1)
    errors.value = next
  }

  /** 关闭指定类别的全部错误 */
  function dismissCategory(category: ErrorCategory): void {
    errors.value = errors.value.filter((e) => e.category !== category)
  }

  /** 清空所有错误 */
  function clear(): void {
    errors.value = []
  }

  const hasErrors = computed<boolean>(() => errors.value.length > 0)
  const lastError = computed<AppError | null>(() => {
    const list = errors.value
    return list.length > 0 ? (list[list.length - 1] ?? null) : null
  })

  return {
    errors,
    hasErrors,
    lastError,
    report,
    dismiss,
    dismissCategory,
    clear
  }
}
