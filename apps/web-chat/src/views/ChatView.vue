<script setup lang="ts">
// ChatView：聊天页（顶部 SessionHeader + 中间 MessageList + 底部 MessageInput + 右侧预留事件组件位）
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'
import { useMessageStore, type ChatMessage } from '@/stores/message'
import SessionHeader from '@/components/SessionHeader.vue'
import MessageList from '@/components/MessageList.vue'
import MessageInput from '@/components/MessageInput.vue'

const props = defineProps<{
  sessionId: string
}>()

const router = useRouter()
const sessionStore = useSessionStore()
const messageStore = useMessageStore()

const { currentSession, loading: sessionLoading } = storeToRefs(sessionStore)
const isLoading = ref<boolean>(false)

/** 当前 session 的消息列表（响应式） */
const messages = computed<ChatMessage[]>(() =>
  messageStore.listBySession(props.sessionId)
)

/** session 是否处于可输入状态 */
const inputDisabled = computed<boolean>(
  () => !currentSession.value || currentSession.value.status === 'closed'
)

/** 加载当前 session 元数据（如本地无缓存则请求） */
async function ensureSession(): Promise<void> {
  if (currentSession.value?.session_id === props.sessionId) return
  sessionStore.select(props.sessionId)
  // 若列表里没有该 session，主动拉取一次
  const exists = sessionStore.sessions.find((s) => s.session_id === props.sessionId)
  if (!exists) {
    isLoading.value = true
    try {
      // 通过 store 内的 api 间接拿：复用 listSessions 兜底（简化处理）
      // 实际项目中可暴露 getSession 到 store；这里不增加 store 体积
      await sessionStore.load()
    } catch {
      // 静默
    } finally {
      isLoading.value = false
    }
  }
}

onMounted(() => {
  void ensureSession()
})

watch(
  () => props.sessionId,
  () => {
    void ensureSession()
  }
)

/** 返回列表 */
function onBack(): void {
  void router.push({ name: 'session-list' })
}

/** 取消任务 */
async function onCancel(sessionId: string): Promise<void> {
  try {
    await sessionStore.cancel(sessionId, 'user_requested')
  } catch {
    // 错误已在 store
  }
}

/** 发送消息（当前阶段仅做本地追加；真实 Run 启动由 WT-E1/E2 集成后接入） */
function onSend(content: string): void {
  if (!props.sessionId) return
  const msg: ChatMessage = {
    id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    session_id: props.sessionId,
    role: 'user',
    content,
    created_at: new Date().toISOString()
  }
  messageStore.append(msg)
}
</script>

<template>
  <div
    class="h-full flex flex-col"
    data-testid="chat-view"
  >
    <SessionHeader
      :session="currentSession"
      :is-loading="isLoading || sessionLoading"
      @back="onBack"
      @cancel="onCancel"
    />

    <div class="flex-1 flex min-h-0">
      <!-- 左侧：消息流 + 输入 -->
      <div class="flex-1 flex flex-col min-w-0">
        <MessageList :messages="messages" />
        <MessageInput
          :disabled="inputDisabled"
          placeholder="输入消息，Enter 发送"
          @send="onSend"
        />
      </div>

      <!-- 右侧：业务事件组件预留位（WT-E3 接入 RoutePanel / CitationWidget / ChartWidget） -->
      <aside
        class="w-80 border-l border-bg-border bg-bg-panel/30 hidden lg:flex flex-col"
        data-testid="event-panel"
      >
        <div class="px-4 py-3 border-b border-bg-border">
          <h2 class="text-fg-primary text-sm font-medium">
            业务事件
          </h2>
          <p class="text-fg-muted text-xs mt-1">
            WT-E3 组件挂载点
          </p>
        </div>
        <div class="flex-1 flex items-center justify-center p-4 text-fg-muted text-xs text-center">
          RoutePanel / CitationWidget / ChartWidget 将在 Wave 3 WT-E3 接入
        </div>
      </aside>
    </div>
  </div>
</template>
