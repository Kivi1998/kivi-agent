<script setup lang="ts">
// SessionHeader 组件：session 标题 + 状态 + 取消按钮
import { computed } from 'vue'
import type { SessionInfo } from '@/types/api'

const props = defineProps<{
  session: SessionInfo | null
  isLoading?: boolean
}>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'cancel', sessionId: string): void
}>()

const canCancel = computed<boolean>(
  () => !!props.session && props.session.status === 'active'
)
</script>

<template>
  <header
    class="border-b border-bg-border bg-bg-panel px-4 py-3 flex items-center justify-between"
    data-testid="session-header"
  >
    <div class="flex items-center gap-3 min-w-0">
      <button
        class="text-fg-muted hover:text-fg-primary text-sm"
        data-testid="back-btn"
        @click="emit('back')"
      >
        ← 返回
      </button>
      <div
        v-if="session"
        class="min-w-0"
      >
        <div class="text-fg-primary text-sm font-medium truncate">
          {{ session.goal || '(无目标)' }}
        </div>
        <div class="text-fg-muted text-xs">
          {{ session.session_id }}
          <span
            class="ml-2 px-2 py-0.5 rounded text-xs"
            :class="{
              'bg-accent-green/20 text-accent-green': session.status === 'active',
              'bg-accent-yellow/20 text-accent-yellow':
                session.status === 'waiting_for_input',
              'bg-fg-muted/20 text-fg-muted': session.status === 'closed'
            }"
            :data-testid="`header-status-${session.session_id}`"
          >
            {{ session.status }}
          </span>
        </div>
      </div>
      <div
        v-else-if="isLoading"
        class="text-fg-muted text-sm"
      >
        加载中...
      </div>
      <div
        v-else
        class="text-fg-muted text-sm"
      >
        未选中 session
      </div>
    </div>
    <div class="flex items-center gap-2">
      <button
        v-if="canCancel"
        class="px-3 py-1.5 text-xs text-accent-red border border-accent-red/40 rounded hover:bg-accent-red/10"
        data-testid="header-cancel-btn"
        @click="emit('cancel', session!.session_id)"
      >
        取消任务
      </button>
    </div>
  </header>
</template>
