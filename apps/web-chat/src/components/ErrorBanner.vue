<script setup lang="ts">
// ErrorBanner：顶部错误 banner 列表
//
// 按 category 着色：
//   api       yellow  fetch 失败 / 4xx / 5xx
//   ws        red     WS 断线 / 连接错误
//   business  red     业务错误
//
// 每条带关闭按钮（emit dismiss(index)），
// 顶部还有 "清空全部" 按钮。

import { computed } from 'vue'
import type { AppError } from '../composables/useErrorHandler'

const props = defineProps<{
  errors: AppError[]
}>()

const emit = defineEmits<{
  (e: 'dismiss', index: number): void
  (e: 'clear'): void
}>()

const hasErrors = computed<boolean>(() => props.errors.length > 0)

function categoryClass(category: AppError['category']): string {
  switch (category) {
    case 'api':
      return 'bg-accent-yellow/10 border-accent-yellow text-accent-yellow'
    case 'ws':
      return 'bg-accent-red/10 border-accent-red text-accent-red'
    case 'business':
      return 'bg-accent-red/10 border-accent-red text-accent-red'
    default:
      return 'bg-bg-panel border-bg-border text-fg-primary'
  }
}

function categoryLabel(category: AppError['category']): string {
  switch (category) {
    case 'api':
      return 'API'
    case 'ws':
      return 'WS'
    case 'business':
      return '业务'
    default:
      return '错误'
  }
}
</script>

<template>
  <div
    v-if="hasErrors"
    class="flex flex-col gap-1 p-2 border-b border-bg-border"
    data-testid="error-banner"
  >
    <div class="flex items-center justify-between text-xs text-fg-muted px-1">
      <span>错误（{{ errors.length }}）</span>
      <button
        type="button"
        class="px-2 py-0.5 rounded border border-bg-border hover:border-fg-muted text-fg-muted hover:text-fg-primary"
        data-testid="error-clear-all"
        @click="emit('clear')"
      >
        清空全部
      </button>
    </div>
    <ul
      class="flex flex-col gap-1"
      data-testid="error-list"
    >
      <li
        v-for="(err, idx) in errors"
        :key="`${err.ts}-${idx}`"
        class="flex items-start gap-2 px-2 py-1.5 rounded border text-xs"
        :class="categoryClass(err.category)"
        :data-testid="`error-item-${idx}`"
        :data-category="err.category"
      >
        <span class="font-mono shrink-0">[{{ categoryLabel(err.category) }}]</span>
        <span
          class="flex-1 break-words"
        >
          <span
            v-if="err.code"
            class="font-mono opacity-70 mr-1"
          >{{ err.code }}</span>
          <span>{{ err.message }}</span>
        </span>
        <button
          type="button"
          aria-label="dismiss"
          class="shrink-0 px-1 hover:opacity-80"
          :data-testid="`error-dismiss-${idx}`"
          @click="emit('dismiss', idx)"
        >
          ✕
        </button>
      </li>
    </ul>
  </div>
</template>
