<script setup lang="ts">
// MessageInput 组件：输入框 + 发送按钮
import { ref } from 'vue'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'send', content: string): void
}>()

const text = ref<string>('')

/** 提交消息（trim 后非空才发送） */
function submit(): void {
  const content = text.value.trim()
  if (!content) return
  if (props.disabled) return
  emit('send', content)
  text.value = ''
}

/** 处理键盘事件（Enter 发送，Shift+Enter 换行） */
function onKeydown(ev: KeyboardEvent): void {
  if (ev.key === 'Enter' && !ev.shiftKey) {
    ev.preventDefault()
    submit()
  }
}
</script>

<template>
  <div
    class="border-t border-bg-border bg-bg-panel px-4 py-3"
    data-testid="message-input"
  >
    <div class="flex items-end gap-2">
      <textarea
        v-model="text"
        :disabled="disabled"
        :placeholder="placeholder ?? '输入消息，Enter 发送，Shift+Enter 换行'"
        rows="2"
        class="flex-1 resize-none bg-bg-base border border-bg-border rounded px-3 py-2 text-sm text-fg-primary placeholder-fg-muted focus:outline-none focus:border-accent-cyan disabled:opacity-50"
        data-testid="message-textarea"
        @keydown="onKeydown"
      />
      <button
        :disabled="disabled || !text.trim()"
        class="px-4 py-2 bg-accent-cyan text-bg-base rounded text-sm font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
        data-testid="send-btn"
        @click="submit"
      >
        发送
      </button>
    </div>
  </div>
</template>
