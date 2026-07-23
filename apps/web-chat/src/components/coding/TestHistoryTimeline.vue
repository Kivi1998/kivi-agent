<script setup lang="ts">
// TestHistoryTimeline：coding run 的 pytest 迭代历史
// 每个迭代渲染一行：iter / passed/total / failed / compile / 时间戳
import { computed } from 'vue'
import type { TestRunRecord } from '@/types/api'

const props = defineProps<{
  records: TestRunRecord[]
}>()

const isEmpty = computed<boolean>(() => props.records.length === 0)

/** 时间戳格式化为 HH:mm:ss */
function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

/** "1/1" passed 形式 */
function passedRatio(r: TestRunRecord): string {
  return `${r.tests_passed}/${r.tests_total}`
}
</script>

<template>
  <section
    class="test-history"
    data-testid="test-history-timeline"
  >
    <header class="th-header">
      <h3 class="th-title">
        测试历史
      </h3>
      <span
        v-if="!isEmpty"
        class="th-count"
        data-testid="test-history-count"
      >{{ records.length }} 轮</span>
    </header>

    <div
      v-if="isEmpty"
      class="th-empty"
      data-testid="test-history-empty"
    >
      暂无测试记录
    </div>

    <ol
      v-else
      class="th-list"
      data-testid="test-history-list"
    >
      <li
        v-for="r in records"
        :key="`iter-${r.iteration}-${r.ts}`"
        class="th-item"
        :data-testid="`test-history-iter-${r.iteration}`"
        :data-passed="r.tests_passed === r.tests_total ? 'true' : 'false'"
      >
        <div
          class="th-marker"
          :data-passed="r.tests_passed === r.tests_total ? 'true' : 'false'"
        >
          iter {{ r.iteration }}
        </div>
        <div class="th-body">
          <div class="th-row">
            <span class="th-ratio">
              {{ passedRatio(r) }}
            </span>
            <span
              v-if="r.tests_failed > 0"
              class="th-failed"
            >failed {{ r.tests_failed }}</span>
            <span
              class="th-compile"
              :data-passed="r.compile_passed ? 'true' : 'false'"
            >{{ r.compile_passed ? '✓ 编译' : '✗ 编译' }}</span>
            <span class="th-time">{{ formatTime(r.ts) }}</span>
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.test-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.th-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.th-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.th-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.th-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.th-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.th-item {
  display: flex;
  gap: 12px;
  padding: 8px 10px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-left-width: 3px;
  border-radius: 4px;
  border-left-color: var(--muted-color);
}

.th-item[data-passed="true"] {
  border-left-color: #10b981;
}

.th-item[data-passed="false"] {
  border-left-color: #ef4444;
}

.th-marker {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-color);
  min-width: 50px;
}

.th-marker[data-passed="true"] {
  color: #10b981;
}

.th-marker[data-passed="false"] {
  color: #ef4444;
}

.th-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.th-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #c9d1d9;
}

.th-ratio {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
  color: var(--route-panel-color, #06b6d4);
}

.th-failed {
  color: #ef4444;
  font-size: 12px;
}

.th-compile {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.th-compile[data-passed="true"] {
  background: #064e3b;
  color: #10b981;
}

.th-compile[data-passed="false"] {
  background: #7f1d1d;
  color: #ef4444;
}

.th-time {
  font-size: 11px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin-left: auto;
}
</style>
