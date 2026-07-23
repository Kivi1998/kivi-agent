// Message Pinia store：消息按 sessionId 分桶存储

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/** 消息角色（user / assistant / system） */
export type MessageRole = 'user' | 'assistant' | 'system'

/** 业务消息（与后端 ExecutionContext.messages 字段对齐） */
export interface ChatMessage {
  id: string
  session_id: string
  role: MessageRole
  content: string
  created_at: string
  run_id?: string
}

export const useMessageStore = defineStore('message', () => {
  // ---- state ----
  // messagesBySession: { [sessionId]: ChatMessage[] }
  const messagesBySession = ref<Record<string, ChatMessage[]>>({})

  // ---- getters ----

  /** 获取指定 session 的消息列表（不可变引用） */
  function listBySession(sessionId: string): ChatMessage[] {
    return messagesBySession.value[sessionId] ?? []
  }

  /** 当前 session 消息列表的 computed 工厂（用于组件订阅） */
  function messagesFor(sessionId: string) {
    return computed<ChatMessage[]>(() => {
      return messagesBySession.value[sessionId] ?? []
    })
  }

  // ---- actions ----

  /** 追加一条消息到指定 session */
  function append(msg: ChatMessage): void {
    const list = messagesBySession.value[msg.session_id] ?? []
    messagesBySession.value = {
      ...messagesBySession.value,
      [msg.session_id]: [...list, msg]
    }
  }

  /** 清除指定 session 的所有消息 */
  function clear(sessionId: string): void {
    const next = { ...messagesBySession.value }
    delete next[sessionId]
    messagesBySession.value = next
  }

  /** 清除所有消息 */
  function clearAll(): void {
    messagesBySession.value = {}
  }

  return {
    messagesBySession,
    listBySession,
    messagesFor,
    append,
    clear,
    clearAll
  }
})
