<script setup lang="ts">
// MemoryAuditTimeline：单条记忆的审计历史（按 ts 倒序，chronological 时间线）
// 每条事件：action / actor / ts / detail（JSON）
import { computed } from 'vue'
import type { MemoryAuditEvent } from '@/types/api'

const props = defineProps<{
  events: MemoryAuditEvent[]
  loading?: boolean
  /** 当前 memory_id（仅展示用） */
  memoryId?: string
}>()

const isEmpty = computed<boolean>(
  () => !props.loading && props.events.length === 0
)

/** 倒序：最新事件在上 */
const sortedEvents = computed<MemoryAuditEvent[]>(() => {
  return [...props.events].sort((a, b) => (a.ts < b.ts ? 1 : -1))
})

function actionClass(a: MemoryAuditEvent['action']): string {
  return `mat-action-${a}`
}

function actionLabel(a: MemoryAuditEvent['action']): string {
  switch (a) {
    case 'create':
      return '创建'
    case 'update':
      return '更新'
    case 'delete':
      return '删除'
    case 'archive':
      return '归档'
    case 'expire':
      return '过期'
    case 'dedup_merge':
      return '去重合并'
    case 'read':
      return '读取'
    default:
      return a
  }
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

function detailSummary(d: Record<string, unknown>): string {
  const keys = Object.keys(d)
  if (keys.length === 0) return '—'
  if (keys.length <= 3) {
    return keys.map((k) => `${k}=${JSON.stringify(d[k])}`).join(', ')
  }
  return `${keys.length} 项: ${keys.slice(0, 3).join(', ')}…`
}
</script>

<template>
  <section
    class="memory-audit"
    data-testid="memory-audit-timeline"
  >
    <header class="mat-header">
      <h3 class="mat-title">
        审计历史
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="mat-count"
        data-testid="memory-audit-count"
      >共 {{ events.length }} 条</span>
    </header>

    <div
      v-if="loading"
      class="mat-loading"
      data-testid="memory-audit-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="mat-empty"
      data-testid="memory-audit-empty"
    >
      暂无审计事件
    </div>

    <ol
      v-else
      class="mat-timeline"
      data-testid="memory-audit-events"
    >
      <li
        v-for="e in sortedEvents"
        :key="e.event_id"
        :data-testid="`memory-audit-row-${e.event_id}`"
        :data-action="e.action"
        class="mat-event"
      >
        <div class="mat-dot-col">
          <span :class="['mat-dot', actionClass(e.action)]" />
        </div>
        <div class="mat-body">
          <div class="mat-row-1">
            <span
              :class="['mat-action', actionClass(e.action)]"
              data-testid="memory-audit-row-action"
            >{{ actionLabel(e.action) }}</span>
            <span class="mat-actor">by {{ e.actor }}</span>
            <span class="mat-ts">{{ formatTime(e.ts) }}</span>
          </div>
          <div
            class="mat-detail"
            data-testid="memory-audit-row-detail"
          >
            {{ detailSummary(e.detail) }}
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.memory-audit {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.mat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #1e242e;
  padding-bottom: 6px;
}

.mat-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.mat-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.mat-loading,
.mat-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 14px 0;
  font-size: 13px;
}

.mat-timeline {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  max-height: 360px;
  overflow-y: auto;
}

.mat-event {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #1e242e;
  align-items: start;
}

.mat-event:last-child {
  border-bottom: none;
}

.mat-dot-col {
  display: flex;
  justify-content: center;
  padding-top: 5px;
}

.mat-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #6366f1;
  box-shadow: 0 0 0 3px #11151c;
}

.mat-action-create {
  background: #10b981;
}
.mat-action-update {
  background: #6366f1;
}
.mat-action-delete {
  background: #ef4444;
}
.mat-action-archive {
  background: #94a3b8;
}
.mat-action-expire {
  background: #fbbf24;
}
.mat-action-dedup_merge {
  background: #d946ef;
}
.mat-action-read {
  background: #6b7280;
}

.mat-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.mat-row-1 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mat-action {
  font-weight: 600;
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.mat-action.mat-action-create {
  background: #064e3b;
  color: #10b981;
}
.mat-action.mat-action-update {
  background: #312e81;
  color: #a5b4fc;
}
.mat-action.mat-action-delete {
  background: #7f1d1d;
  color: #fca5a5;
}
.mat-action.mat-action-archive {
  background: #1e293b;
  color: #94a3b8;
}
.mat-action.mat-action-expire {
  background: #4b3a00;
  color: #fbbf24;
}
.mat-action.mat-action-dedup_merge {
  background: #581c87;
  color: #e9d5ff;
}
.mat-action.mat-action-read {
  background: #1e293b;
  color: #6b7280;
}

.mat-actor {
  font-size: 12px;
  color: var(--muted-color);
}

.mat-ts {
  font-size: 11px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin-left: auto;
}

.mat-detail {
  font-size: 11px;
  color: #c9d1d9;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}
</style>
