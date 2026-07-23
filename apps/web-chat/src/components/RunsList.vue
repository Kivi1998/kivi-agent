<script setup lang="ts">
// RunsList：评测运行列表（按时间倒序）
// 表格列：run_id / started_at / case_count / success_count
// 点击行 → emit('select', runId)
import { computed } from 'vue'
import type { RunSummary } from '@/types/api'

const props = defineProps<{
  runs: RunSummary[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', runId: string): void
}>()

/** 列表为空 */
const isEmpty = computed<boolean>(() => props.runs.length === 0)

/** 时间戳格式化为本地可读字符串 */
function formatTime(ts: string | null): string {
  if (!ts) return '(未开始)'
  try {
    const d = new Date(ts)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

/** 计算成功率百分比（用于表格右侧额外展示） */
function rateStr(run: RunSummary): string {
  if (run.case_count === 0) return '—'
  return ((run.success_count / run.case_count) * 100).toFixed(1) + '%'
}

/** 行点击 → 通知上层跳转 */
function onRowClick(runId: string): void {
  emit('select', runId)
}
</script>

<template>
  <section
    class="runs-list"
    data-testid="runs-list"
  >
    <header class="runs-header">
      <h3 class="runs-title">
        评测运行
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="runs-count"
        data-testid="runs-count"
      >共 {{ runs.length }} 条</span>
    </header>

    <div
      v-if="loading"
      class="runs-loading"
      data-testid="runs-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="runs-empty"
      data-testid="runs-empty"
    >
      暂无评测运行
    </div>

    <table
      v-else
      class="runs-table"
      data-testid="runs-table"
    >
      <thead>
        <tr>
          <th>run_id</th>
          <th>started_at</th>
          <th class="num">
            case
          </th>
          <th class="num">
            success
          </th>
          <th class="num">
            rate
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="run in runs"
          :key="run.run_id"
          :data-testid="`runs-row-${run.run_id}`"
          class="runs-row"
          @click="onRowClick(run.run_id)"
        >
          <td class="run-id">
            {{ run.run_id }}
          </td>
          <td>{{ formatTime(run.started_at) }}</td>
          <td class="num">
            {{ run.case_count }}
          </td>
          <td class="num">
            {{ run.success_count }}
          </td>
          <td class="num rate">
            {{ rateStr(run) }}
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.runs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.runs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.runs-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.runs-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.runs-empty,
.runs-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.runs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.runs-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.runs-table td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.runs-table .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.runs-table .rate {
  color: var(--route-panel-color, #06b6d4);
}

.runs-row {
  cursor: pointer;
  transition: background 0.15s;
}

.runs-row:hover {
  background: #1e242e;
}

.run-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--route-panel-color, #06b6d4);
}
</style>
