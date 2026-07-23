<script setup lang="ts">
// ConnectionStatus：WebSocket 连接状态指示器
//
// 5 个状态 → 颜色 + 图标 + 文案
//   connecting     yellow  圆形虚线  连接中…
//   open           green   圆点      已连接
//   reconnecting   yellow  循环      重连中（attempts 次）
//   closed         red     叉号      已断开
//   error          red     三角      连接错误
//
// E2E 钩子：data-testid="connected-status" / "reconnecting-status" /
//   "closed-status" / "error-status" / "connecting-status"

import { computed } from 'vue'
import type { WSState } from '../composables/useWebSocket'

const props = defineProps<{
  state: WSState
  reconnectAttempts?: number
}>()

interface StatusView {
  label: string
  color: 'green' | 'yellow' | 'red' | 'gray'
  icon: 'dot' | 'spinner' | 'cross' | 'alert' | 'loop'
  testId: string
}

const view = computed<StatusView>(() => {
  switch (props.state) {
    case 'connecting':
      return {
        label: '连接中…',
        color: 'yellow',
        icon: 'spinner',
        testId: 'connecting-status'
      }
    case 'open':
      return {
        label: '已连接',
        color: 'green',
        icon: 'dot',
        testId: 'connected-status'
      }
    case 'reconnecting': {
      const n = props.reconnectAttempts ?? 0
      return {
        label: n > 0 ? `重连中（${n}）…` : '重连中…',
        color: 'yellow',
        icon: 'loop',
        testId: 'reconnecting-status'
      }
    }
    case 'closed':
      return {
        label: '已断开',
        color: 'red',
        icon: 'cross',
        testId: 'closed-status'
      }
    case 'error':
      return {
        label: '连接错误',
        color: 'red',
        icon: 'alert',
        testId: 'error-status'
      }
    default:
      return {
        label: '未知',
        color: 'gray',
        icon: 'dot',
        testId: 'unknown-status'
      }
  }
})

const colorClass = computed<string>(() => {
  switch (view.value.color) {
    case 'green':
      return 'text-accent-green border-accent-green'
    case 'yellow':
      return 'text-accent-yellow border-accent-yellow'
    case 'red':
      return 'text-accent-red border-accent-red'
    default:
      return 'text-fg-muted border-bg-border'
  }
})
</script>

<template>
  <div
    class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-mono"
    :class="colorClass"
    :data-testid="view.testId"
    :data-state="props.state"
  >
    <span aria-hidden="true">
      <template v-if="view.icon === 'dot'">●</template>
      <template v-else-if="view.icon === 'spinner'">◌</template>
      <template v-else-if="view.icon === 'loop'">↻</template>
      <template v-else-if="view.icon === 'cross'">✕</template>
      <template v-else-if="view.icon === 'alert'">!</template>
      <template v-else>·</template>
    </span>
    <span>{{ view.label }}</span>
  </div>
</template>
