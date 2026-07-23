<script setup lang="ts">
// SessionList 组件：渲染 session 卡片列表
import { computed } from 'vue'
import type { SessionInfo } from '@/types/api'

const props = defineProps<{
  sessions: SessionInfo[]
}>()

const emit = defineEmits<{
  (e: 'select', sessionId: string): void
  (e: 'cancel', sessionId: string): void
}>()

/** 格式化 created_at（ISO 8601 → 本地时间字符串） */
function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const hasItems = computed<boolean>(() => props.sessions.length > 0)
</script>

<template>
  <div class="flex flex-col gap-2">
    <p
      v-if="!hasItems"
      class="text-fg-muted text-sm py-8 text-center"
      data-testid="empty-state"
    >
      暂无会话，点上方"新建"按钮开始
    </p>
    <ul
      v-else
      class="flex flex-col gap-2"
      data-testid="session-list"
    >
      <li
        v-for="s in sessions"
        :key="s.session_id"
        class="bg-bg-panel border border-bg-border rounded p-3 hover:border-accent-cyan cursor-pointer transition-colors"
        :data-testid="`session-item-${s.session_id}`"
        @click="emit('select', s.session_id)"
      >
        <div class="flex items-center justify-between">
          <div class="flex-1 min-w-0">
            <div class="text-fg-primary text-sm font-medium truncate">
              {{ s.goal || '(无目标)' }}
            </div>
            <div class="text-fg-muted text-xs mt-1">
              {{ s.session_id }} · {{ formatDate(s.created_at) }}
            </div>
          </div>
          <div class="flex items-center gap-2 ml-3">
            <span
              class="text-xs px-2 py-0.5 rounded"
              :class="{
                'bg-accent-green/20 text-accent-green': s.status === 'active',
                'bg-accent-yellow/20 text-accent-yellow':
                  s.status === 'waiting_for_input',
                'bg-fg-muted/20 text-fg-muted': s.status === 'closed'
              }"
              :data-testid="`session-status-${s.session_id}`"
            >
              {{ s.status }}
            </span>
            <button
              v-if="s.status === 'active'"
              class="text-xs text-accent-red hover:underline"
              :data-testid="`cancel-btn-${s.session_id}`"
              @click.stop="emit('cancel', s.session_id)"
            >
              取消
            </button>
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
