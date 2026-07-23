<script setup lang="ts">
// RunsList (coding)：coding run 列表（按开始时间倒序）
// 表格列：run_id / task 摘要 / test_file / iteration / success / started_at
// 点击行 → emit('select', runId)
import { computed } from 'vue'
import type { CodingRunItem } from '@/types/api'

const props = defineProps<{
  runs: CodingRunItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', runId: string): void
}>()

const isEmpty = computed<boolean>(() => props.runs.length === 0)

function formatTime(ts: string | null): string {
  if (!ts) return '(未开始)'
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

/** task 截前 50 字 */
function taskShort(task: string): string {
  if (task.length <= 50) return task
  return task.slice(0, 50) + '…'
}

function onRowClick(runId: string): void {
  emit('select', runId)
}
</script>

<template>
  <section
    class="cruns-list"
    data-testid="cruns-list"
  >
    <header class="cruns-header">
      <h3 class="cruns-title">
        Coding Run
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="cruns-count"
        data-testid="cruns-count"
      >共 {{ runs.length }} 条</span>
    </header>

    <div
      v-if="loading"
      class="cruns-loading"
      data-testid="cruns-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="cruns-empty"
      data-testid="cruns-empty"
    >
      暂无 coding run
    </div>

    <table
      v-else
      class="cruns-table"
      data-testid="cruns-table"
    >
      <thead>
        <tr>
          <th>run_id</th>
          <th>task</th>
          <th>test_file</th>
          <th class="num">
            iters
          </th>
          <th>success</th>
          <th>started_at</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="r in runs"
          :key="r.run_id"
          :data-testid="`cruns-row-${r.run_id}`"
          :data-success="r.success ? 'true' : 'false'"
          class="cruns-row"
          @click="onRowClick(r.run_id)"
        >
          <td class="run-id">
            {{ r.run_id }}
          </td>
          <td class="task">
            {{ taskShort(r.task) }}
          </td>
          <td class="test-file">
            {{ r.test_file }}
          </td>
          <td class="num">
            {{ r.iteration_count }}
          </td>
          <td>
            <span :class="['badge', r.success ? 'badge-ok' : 'badge-fail']">
              {{ r.success ? '✓' : '✗' }}
            </span>
          </td>
          <td>{{ formatTime(r.started_at) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.cruns-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.cruns-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.cruns-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.cruns-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.cruns-empty,
.cruns-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.cruns-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.cruns-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.cruns-table td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.cruns-table .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.cruns-row {
  cursor: pointer;
  transition: background 0.15s;
}

.cruns-row:hover {
  background: #1e242e;
}

.run-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #d946ef;
}

.task {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.test-file {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--route-panel-color, #06b6d4);
  font-size: 12px;
}

.badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.badge-ok {
  background: #064e3b;
  color: #10b981;
}

.badge-fail {
  background: #7f1d1d;
  color: #ef4444;
}
</style>
