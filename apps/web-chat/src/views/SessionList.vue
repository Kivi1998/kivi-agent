<script setup lang="ts">
// SessionList 视图：列出所有 session + 新建按钮
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useSessionStore } from '@/stores/session'
import SessionListComponent from '@/components/SessionList.vue'

const router = useRouter()
const store = useSessionStore()
const { sessions, loading, error, hasSessions } = storeToRefs(store)

const newGoal = ref<string>('')

/** 挂载时拉取 session 列表（失败也不阻塞 UI） */
onMounted(async () => {
  try {
    await store.load()
  } catch {
    // 错误已在 store.error 中
  }
})

/** 进入聊天页 */
function onSelect(sessionId: string): void {
  store.select(sessionId)
  void router.push({ name: 'chat', params: { sessionId } })
}

/** 取消 session */
async function onCancel(sessionId: string): Promise<void> {
  try {
    await store.cancel(sessionId)
  } catch {
    // 错误已存
  }
}

/** 创建新 session */
async function onCreate(): Promise<void> {
  const goal = newGoal.value.trim()
  if (!goal) return
  try {
    const info = await store.add(goal)
    newGoal.value = ''
    void router.push({ name: 'chat', params: { sessionId: info.session_id } })
  } catch {
    // 错误已存
  }
}
</script>

<template>
  <div
    class="h-full flex flex-col max-w-3xl mx-auto w-full px-6 py-6"
    data-testid="session-list-view"
  >
    <h1 class="text-xl font-semibold text-fg-primary mb-1">
      会话
    </h1>
    <p class="text-fg-muted text-sm mb-4">
      选择一个会话继续，或新建一个
    </p>

    <div class="flex gap-2 mb-4">
      <input
        v-model="newGoal"
        type="text"
        placeholder="新会话目标，例如：对比网上关于 RAG 的最新文章和我们内部知识库"
        class="flex-1 bg-bg-panel border border-bg-border rounded px-3 py-2 text-sm text-fg-primary placeholder-fg-muted focus:outline-none focus:border-accent-cyan"
        data-testid="new-goal-input"
        @keydown.enter="onCreate"
      >
      <button
        :disabled="!newGoal.trim() || loading"
        class="px-4 py-2 bg-accent-cyan text-bg-base rounded text-sm font-medium hover:opacity-90 disabled:opacity-40"
        data-testid="create-btn"
        @click="onCreate"
      >
        新建
      </button>
    </div>

    <div
      v-if="error"
      class="text-accent-red text-sm mb-3"
      data-testid="error-banner"
    >
      {{ error }}
    </div>

    <div
      v-if="loading"
      class="text-fg-muted text-sm mb-3"
    >
      加载中...
    </div>

    <SessionListComponent
      :sessions="sessions"
      @select="onSelect"
      @cancel="onCancel"
    />

    <p
      v-if="!hasSessions && !loading"
      class="text-fg-muted text-xs mt-6 text-center"
    >
      提示：当前无会话；输入目标并点"新建"开始
    </p>
  </div>
</template>
