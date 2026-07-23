<script setup lang="ts">
// MemoryList：记忆列表（带 status / memory_type / source 过滤）
// 表格列：id / type / status / importance / source / created_at
// 行点击 → emit('select', id)
import { computed } from 'vue'
import type { MemoryItem, MemoryStatus, MemoryType } from '@/types/api'
import { MEMORY_STATUS_LABELS, MEMORY_TYPE_LABELS } from '@/api/memory'

const props = defineProps<{
  items: MemoryItem[]
  loading?: boolean
  filterStatus?: MemoryStatus | ''
  filterType?: MemoryType | ''
  filterSource?: string
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'update:filterStatus', v: MemoryStatus | ''): void
  (e: 'update:filterType', v: MemoryType | ''): void
  (e: 'update:filterSource', v: string): void
}>()

const isEmpty = computed<boolean>(() => props.items.length === 0)

function onRowClick(id: string): void {
  emit('select', id)
}

function onStatusChange(e: Event): void {
  const v = (e.target as HTMLSelectElement).value
  emit('update:filterStatus', v as MemoryStatus | '')
}

function onTypeChange(e: Event): void {
  const v = (e.target as HTMLSelectElement).value
  emit('update:filterType', v as MemoryType | '')
}

function onSourceInput(e: Event): void {
  const v = (e.target as HTMLInputElement).value
  emit('update:filterSource', v)
}

function formatTime(ts: string | null): string {
  if (!ts) return '(未设置)'
  try {
    return new Date(ts).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

function importancePct(v: number): string {
  return (v * 100).toFixed(0) + '%'
}

function importanceClass(v: number): string {
  if (v >= 0.7) return 'imp-high'
  if (v >= 0.4) return 'imp-mid'
  return 'imp-low'
}

function statusClass(s: MemoryStatus): string {
  return `badge-status-${s}`
}
</script>

<template>
  <section
    class="memory-list"
    data-testid="memory-list"
  >
    <header class="ml-header">
      <h3 class="ml-title">
        记忆列表
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="ml-count"
        data-testid="memory-list-count"
      >共 {{ items.length }} 条</span>
    </header>

    <div
      class="ml-filters"
      data-testid="memory-list-filters"
    >
      <label class="ml-filter">
        <span>状态</span>
        <select
          :value="filterStatus ?? ''"
          data-testid="memory-filter-status"
          @change="onStatusChange"
        >
          <option value="">
            全部
          </option>
          <option value="active">
            活跃
          </option>
          <option value="pending">
            待处理
          </option>
          <option value="archived">
            已归档
          </option>
          <option value="expired">
            已过期
          </option>
        </select>
      </label>
      <label class="ml-filter">
        <span>类型</span>
        <select
          :value="filterType ?? ''"
          data-testid="memory-filter-type"
          @change="onTypeChange"
        >
          <option value="">
            全部
          </option>
          <option value="user">
            用户
          </option>
          <option value="feedback">
            反馈
          </option>
          <option value="project">
            项目
          </option>
          <option value="reference">
            参考
          </option>
          <option value="task">
            任务
          </option>
        </select>
      </label>
      <label class="ml-filter ml-filter-source">
        <span>来源</span>
        <input
          :value="filterSource ?? ''"
          type="text"
          placeholder="如 session-abc"
          data-testid="memory-filter-source"
          @input="onSourceInput"
        >
      </label>
    </div>

    <div
      v-if="loading"
      class="ml-loading"
      data-testid="memory-list-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="ml-empty"
      data-testid="memory-list-empty"
    >
      暂无记忆
    </div>

    <table
      v-else
      class="ml-table"
      data-testid="memory-list-table"
    >
      <thead>
        <tr>
          <th>id</th>
          <th>type</th>
          <th>status</th>
          <th class="num">
            importance
          </th>
          <th>source</th>
          <th>created_at</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in items"
          :key="item.id"
          :data-testid="`memory-row-${item.id}`"
          :data-status="item.status"
          class="ml-row"
          @click="onRowClick(item.id)"
        >
          <td class="ml-id">
            {{ item.id }}
          </td>
          <td>{{ MEMORY_TYPE_LABELS[item.memory_type] }}</td>
          <td>
            <span :class="['badge', statusClass(item.status)]">
              {{ MEMORY_STATUS_LABELS[item.status] }}
            </span>
          </td>
          <td class="num">
            <span :class="['imp', importanceClass(item.importance)]">{{ importancePct(item.importance) }}</span>
          </td>
          <td class="ml-source">
            {{ item.source || '(无)' }}
          </td>
          <td>{{ formatTime(item.created_at) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.ml-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ml-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.ml-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.ml-filters {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: flex-end;
}

.ml-filter {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--muted-color);
}

.ml-filter-source {
  flex: 1;
  min-width: 200px;
}

.ml-filter select,
.ml-filter input {
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 5px 8px;
  font-size: 12px;
  font-family: inherit;
}

.ml-filter select:focus,
.ml-filter input:focus {
  outline: 1px solid #6366f1;
  border-color: #6366f1;
}

.ml-empty,
.ml-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.ml-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ml-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 11px;
}

.ml-table td {
  padding: 7px 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.ml-table .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.ml-row {
  cursor: pointer;
  transition: background 0.15s;
}

.ml-row:hover {
  background: #1e242e;
}

.ml-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #6366f1;
  font-size: 11px;
}

.ml-source {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--muted-color);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.badge-status-active {
  background: #064e3b;
  color: #10b981;
}

.badge-status-pending {
  background: #4b3a00;
  color: #fbbf24;
}

.badge-status-archived {
  background: #1e293b;
  color: #94a3b8;
}

.badge-status-expired {
  background: #7f1d1d;
  color: #ef4444;
}

.imp {
  font-weight: 600;
}

.imp-high {
  color: #10b981;
}

.imp-mid {
  color: #fbbf24;
}

.imp-low {
  color: #94a3b8;
}
</style>
