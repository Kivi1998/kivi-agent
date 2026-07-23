<script setup lang="ts">
// CancelButton：红色"停止"按钮
//
// 状态：
// - idle        红色"停止"
// - cancelling  loading + "取消中…"
//
// 接收 sessionId + onCancel 回调，
// 父组件用 useCancel 处理实际 API 调用。
// E2E 钩子：data-testid="cancel-button" / "cancel-button-loading"

import { computed } from 'vue'

const props = defineProps<{
  sessionId: string
  isCancelling: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
}>()

const isDisabled = computed<boolean>(
  () => props.isCancelling || !!props.disabled
)

const label = computed<string>(() =>
  props.isCancelling ? '取消中…' : '停止'
)

const testId = computed<string>(() =>
  props.isCancelling ? 'cancel-button-loading' : 'cancel-button'
)

function onClick(): void {
  if (isDisabled.value) return
  emit('cancel')
}
</script>

<template>
  <button
    type="button"
    :disabled="isDisabled"
    class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border bg-accent-red/10 text-accent-red border-accent-red hover:bg-accent-red/20 disabled:opacity-50 disabled:cursor-not-allowed"
    :data-testid="testId"
    :data-session-id="props.sessionId"
    :data-cancelling="String(props.isCancelling)"
    @click="onClick"
  >
    <span aria-hidden="true">
      <template v-if="isCancelling">◌</template>
      <template v-else>■</template>
    </span>
    <span>{{ label }}</span>
  </button>
</template>
