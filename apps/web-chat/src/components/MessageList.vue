<script setup lang="ts">
// MessageList 组件：渲染消息流
import { computed } from 'vue'
import type { ChatMessage } from '@/stores/message'

const props = defineProps<{
  messages: ChatMessage[]
}>()

const hasMessages = computed<boolean>(() => props.messages.length > 0)
</script>

<template>
  <div
    class="flex-1 overflow-y-auto px-4 py-3"
    data-testid="message-list-container"
  >
    <p
      v-if="!hasMessages"
      class="text-fg-muted text-sm text-center py-12"
      data-testid="empty-messages"
    >
      暂无消息，在下方输入框开始对话
    </p>
    <ul
      v-else
      class="flex flex-col gap-3"
      data-testid="message-list"
    >
      <li
        v-for="m in messages"
        :key="m.id"
        class="flex"
        :class="{
          'justify-end': m.role === 'user',
          'justify-start': m.role !== 'user'
        }"
        :data-testid="`message-${m.id}`"
      >
        <div
          class="max-w-[80%] rounded-lg px-3 py-2 text-sm"
          :class="{
            'bg-accent-cyan/20 text-fg-primary': m.role === 'user',
            'bg-bg-panel border border-bg-border text-fg-primary':
              m.role === 'assistant',
            'bg-fg-muted/10 text-fg-muted italic': m.role === 'system'
          }"
        >
          <div class="whitespace-pre-wrap break-words">
            {{ m.content }}
          </div>
        </div>
      </li>
    </ul>
  </div>
</template>
