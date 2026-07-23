<script setup lang="ts">
// CaseTable：单 run 的 case 列表
// 列：case_id / success / tool count / sources count / final answer 摘要
// 点击行 → emit('select', { runId, caseId })
import { computed } from 'vue'
import type { CaseEvalResult } from '@/types/api'

const props = defineProps<{
  cases: CaseEvalResult[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', caseId: string): void
}>()

const isEmpty = computed<boolean>(() => props.cases.length === 0)

/** 工具调用数（兼容字段缺失） */
function toolCount(c: CaseEvalResult): number {
  return c.tool_calls?.length ?? 0
}

/** RAG 引用数（兼容字段缺失） */
function sourcesCount(c: CaseEvalResult): number {
  return c.rag_sources?.length ?? 0
}

/** final answer 摘要（截前 80 字） */
function answerSummary(c: CaseEvalResult): string {
  const ans = c.final_answer ?? ''
  if (ans.length <= 80) return ans
  return ans.slice(0, 80) + '…'
}

function onRowClick(caseId: string): void {
  emit('select', caseId)
}
</script>

<template>
  <section
    class="case-table"
    data-testid="case-table"
  >
    <header class="case-header">
      <h3 class="case-title">
        Case 列表
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="case-count"
        data-testid="case-count"
      >共 {{ cases.length }} 个</span>
    </header>

    <div
      v-if="loading"
      class="case-loading"
      data-testid="case-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="case-empty"
      data-testid="case-empty"
    >
      暂无 case
    </div>

    <table
      v-else
      class="case-table-grid"
      data-testid="case-table-grid"
    >
      <thead>
        <tr>
          <th>case_id</th>
          <th>success</th>
          <th class="num">
            tools
          </th>
          <th class="num">
            sources
          </th>
          <th>answer 摘要</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="c in cases"
          :key="c.case_id"
          :data-testid="`case-row-${c.case_id}`"
          :data-success="c.success ? 'true' : 'false'"
          class="case-row"
          @click="onRowClick(c.case_id)"
        >
          <td class="case-id">{{ c.case_id }}</td>
          <td>
            <span :class="['badge', c.success ? 'badge-ok' : 'badge-fail']">
              {{ c.success ? '✓' : '✗' }}
            </span>
          </td>
          <td class="num">{{ toolCount(c) }}</td>
          <td class="num">{{ sourcesCount(c) }}</td>
          <td class="answer">{{ answerSummary(c) || '(无)' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.case-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.case-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.case-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.case-empty,
.case-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.case-table-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.case-table-grid th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.case-table-grid td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.case-table-grid .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.case-row {
  cursor: pointer;
  transition: background 0.15s;
}

.case-row:hover {
  background: #1e242e;
}

.case-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--route-panel-color, #06b6d4);
}

.answer {
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
