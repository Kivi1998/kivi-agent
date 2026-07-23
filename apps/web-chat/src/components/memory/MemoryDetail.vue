<script setup lang="ts">
// MemoryDetail：单条记忆详情（content + 元信息 + 操作按钮）
// 按钮：编辑 / 归档 / 删除（emit 通知上层）
import { computed } from 'vue'
import type { MemoryItem } from '@/types/api'
import { MEMORY_STATUS_LABELS, MEMORY_TYPE_LABELS } from '@/api/memory'

const props = defineProps<{
  item: MemoryItem | null
}>()

const emit = defineEmits<{
  (e: 'edit', id: string): void
  (e: 'archive', id: string): void
  (e: 'delete', id: string): void
}>()

/** 当前 item 的本地非空引用（v-else 分支保证非空） */
const current = computed<MemoryItem | null>(() => props.item)

function formatTime(ts: string | null): string {
  if (!ts) return '(未设置)'
  try {
    return new Date(ts).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

function importancePct(v: number): string {
  return (v * 100).toFixed(1) + '%'
}

function statusClass(s: MemoryItem['status']): string {
  return `md-status-${s}`
}

function onEdit(): void {
  if (props.item) emit('edit', props.item.id)
}

function onArchive(): void {
  if (props.item) emit('archive', props.item.id)
}

function onDelete(): void {
  if (props.item) emit('delete', props.item.id)
}
</script>

<template>
  <section
    class="memory-detail"
    data-testid="memory-detail"
  >
    <div
      v-if="!current"
      class="md-empty"
      data-testid="memory-detail-empty"
    >
      请从左侧选择一条记忆查看详情
    </div>

    <div
      v-else
      class="md-body"
      data-testid="memory-detail-body"
    >
      <header class="md-header">
        <div class="md-id">
          <span class="md-label">id</span>
          <span
            class="md-value"
            data-testid="memory-detail-id"
          >{{ current.id }}</span>
        </div>
        <div class="md-actions">
          <button
            type="button"
            class="md-btn md-btn-edit"
            data-testid="memory-detail-edit"
            @click="onEdit"
          >
            编辑
          </button>
          <button
            v-if="current.status !== 'archived'"
            type="button"
            class="md-btn md-btn-archive"
            data-testid="memory-detail-archive"
            @click="onArchive"
          >
            归档
          </button>
          <button
            type="button"
            class="md-btn md-btn-delete"
            data-testid="memory-detail-delete"
            @click="onDelete"
          >
            删除
          </button>
        </div>
      </header>

      <div class="md-content-wrap">
        <div class="md-label">
          content
        </div>
        <pre
          class="md-content"
          data-testid="memory-detail-content"
        >{{ current.content }}</pre>
      </div>

      <dl class="md-meta">
        <div class="md-meta-row">
          <dt>type</dt>
          <dd data-testid="memory-detail-type">
            {{ MEMORY_TYPE_LABELS[current.memory_type] }}
          </dd>
        </div>
        <div class="md-meta-row">
          <dt>status</dt>
          <dd>
            <span
              :class="['badge', statusClass(current.status)]"
              data-testid="memory-detail-status"
            >{{ MEMORY_STATUS_LABELS[current.status] }}</span>
          </dd>
        </div>
        <div class="md-meta-row">
          <dt>importance</dt>
          <dd data-testid="memory-detail-importance">
            {{ importancePct(current.importance) }}
          </dd>
        </div>
        <div class="md-meta-row">
          <dt>source</dt>
          <dd data-testid="memory-detail-source">
            {{ current.source || '(无)' }}
          </dd>
        </div>
        <div class="md-meta-row">
          <dt>created_at</dt>
          <dd>{{ formatTime(current.created_at) }}</dd>
        </div>
        <div class="md-meta-row">
          <dt>updated_at</dt>
          <dd>{{ formatTime(current.updated_at) }}</dd>
        </div>
        <div class="md-meta-row">
          <dt>expires_at</dt>
          <dd>{{ formatTime(current.expires_at) }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
.memory-detail {
  display: flex;
  flex-direction: column;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
  min-height: 280px;
}

.md-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 60px 0;
  font-size: 13px;
}

.md-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.md-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #1e242e;
  padding-bottom: 10px;
}

.md-id {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.md-label {
  font-size: 11px;
  color: var(--muted-color);
  text-transform: uppercase;
  font-weight: 500;
}

.md-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #6366f1;
  font-size: 13px;
}

.md-actions {
  display: flex;
  gap: 6px;
}

.md-btn {
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.md-btn:hover {
  background: #1e242e;
}

.md-btn-archive {
  color: #fbbf24;
  border-color: #4b3a00;
}

.md-btn-delete {
  color: #ef4444;
  border-color: #7f1d1d;
}

.md-content-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.md-content {
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 10px 12px;
  color: #c9d1d9;
  font-size: 13px;
  line-height: 1.5;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  max-height: 280px;
  overflow-y: auto;
}

.md-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 16px;
  margin: 0;
  padding: 0;
}

.md-meta-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 0;
  border-bottom: 1px solid #1e242e;
}

.md-meta-row dt {
  font-size: 10px;
  color: var(--muted-color);
  text-transform: uppercase;
  font-weight: 500;
  margin: 0;
}

.md-meta-row dd {
  font-size: 12px;
  color: #c9d1d9;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.md-status-active {
  background: #064e3b;
  color: #10b981;
}

.md-status-pending {
  background: #4b3a00;
  color: #fbbf24;
}

.md-status-archived {
  background: #1e293b;
  color: #94a3b8;
}

.md-status-expired {
  background: #7f1d1d;
  color: #ef4444;
}
</style>
