<script setup lang="ts">
// IterationCountBadge：迭代轮数徽章
// 颜色：1 绿 / 2 黄 / ≥3 红；展示 iter 数 + 圆点
import { computed } from 'vue'

const props = defineProps<{
  /** 迭代轮数（≥0） */
  iterations: number
}>()

/** 颜色级别：1 绿 / 2 黄 / ≥3 红 / 0 灰 */
const colorLevel = computed<'green' | 'yellow' | 'red' | 'gray'>(() => {
  if (props.iterations <= 0) return 'gray'
  if (props.iterations === 1) return 'green'
  if (props.iterations === 2) return 'yellow'
  return 'red'
})

const label = computed<string>(() => {
  if (props.iterations <= 0) return '未运行'
  if (props.iterations === 1) return '1 轮（一次过）'
  return `${props.iterations} 轮`
})
</script>

<template>
  <span
    class="iter-badge"
    :data-level="colorLevel"
    :data-testid="`iter-badge-${iterations}`"
  >
    <span class="iter-dot" />
    {{ label }}
  </span>
</template>

<style scoped>
.iter-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  border: 1px solid;
}

.iter-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.iter-badge[data-level="green"] {
  background: #064e3b;
  color: #10b981;
  border-color: #10b981;
}
.iter-badge[data-level="green"] .iter-dot {
  background: #10b981;
}

.iter-badge[data-level="yellow"] {
  background: #422006;
  color: #eab308;
  border-color: #eab308;
}
.iter-badge[data-level="yellow"] .iter-dot {
  background: #eab308;
}

.iter-badge[data-level="red"] {
  background: #7f1d1d;
  color: #ef4444;
  border-color: #ef4444;
}
.iter-badge[data-level="red"] .iter-dot {
  background: #ef4444;
}

.iter-badge[data-level="gray"] {
  background: #1e242e;
  color: #6b7280;
  border-color: #2a313c;
}
.iter-badge[data-level="gray"] .iter-dot {
  background: #6b7280;
}
</style>
