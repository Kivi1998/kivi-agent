// Session Pinia store：sessions 列表 + currentSession

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { SessionApi } from '@/api/session'
import type { SessionInfo } from '@/types/api'

/** Session store 工厂参数（可注入 API 客户端，便于测试） */
export interface SessionStoreOptions {
  api: SessionApi
}

export const useSessionStore = defineStore('session', () => {
  // ---- state ----
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const userId = ref<string>('default-user')

  // 内部 API 引用（构造时注入；setApi 用于延迟注入）
  let apiRef: SessionApi | null = null

  /** 注入 API 客户端（首次调用前必须） */
  function setApi(api: SessionApi): void {
    apiRef = api
  }

  function requireApi(): SessionApi {
    if (!apiRef) {
      throw new Error('session store: api not set. Call setApi() first.')
    }
    return apiRef
  }

  // ---- getters ----
  const currentSession = computed<SessionInfo | null>(() => {
    if (!currentSessionId.value) return null
    return sessions.value.find((s) => s.session_id === currentSessionId.value) ?? null
  })

  const hasSessions = computed<boolean>(() => sessions.value.length > 0)

  // ---- actions ----

  /** 加载 user 的所有 session（覆盖本地列表） */
  async function load(targetUserId?: string): Promise<void> {
    const uid = targetUserId ?? userId.value
    if (targetUserId) userId.value = targetUserId
    loading.value = true
    error.value = null
    try {
      const list = await requireApi().listSessions(uid)
      sessions.value = list
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  /** 创建一个新 session（启动后端 Run） */
  async function add(goal: string): Promise<SessionInfo> {
    error.value = null
    const info = await requireApi().startSession({
      user_id: userId.value,
      goal
    })
    sessions.value = [info, ...sessions.value]
    currentSessionId.value = info.session_id
    return info
  }

  /** 选中某个 session（仅本地状态切换） */
  function select(sessionId: string | null): void {
    currentSessionId.value = sessionId
  }

  /** 取消当前选中的 session */
  async function cancel(sessionId: string, reason?: string): Promise<void> {
    error.value = null
    await requireApi().cancelSession(sessionId, reason)
    // 乐观更新本地状态
    sessions.value = sessions.value.map((s) =>
      s.session_id === sessionId ? { ...s, status: 'closed' } : s
    )
  }

  /** 清除错误状态 */
  function clearError(): void {
    error.value = null
  }

  return {
    // state
    sessions,
    currentSessionId,
    loading,
    error,
    userId,
    // getters
    currentSession,
    hasSessions,
    // actions
    setApi,
    load,
    add,
    select,
    cancel,
    clearError
  }
})
