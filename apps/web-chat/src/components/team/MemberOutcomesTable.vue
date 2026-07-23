<script setup lang="ts">
// MemberOutcomesTable：成员最终结果表
// 列：member_id / role / success / steps / tool_calls / final_answer 摘要
import { computed } from 'vue'
import type { MemberOutcome } from '@/types/api'

const props = defineProps<{
  outcomes: MemberOutcome[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', memberId: string): void
}>()

const isEmpty = computed<boolean>(() => props.outcomes.length === 0)

/** final answer 摘要（截前 80 字） */
function answerSummary(o: MemberOutcome): string {
  const ans = o.final_answer ?? ''
  if (ans.length <= 80) return ans
  return ans.slice(0, 80) + '…'
}

function onRowClick(memberId: string): void {
  emit('select', memberId)
}
</script>

<template>
  <section
    class="outcomes-table"
    data-testid="member-outcomes-table"
  >
    <header class="ot-header">
      <h3 class="ot-title">
        成员结果
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="ot-count"
        data-testid="member-outcomes-count"
      >共 {{ outcomes.length }} 成员</span>
    </header>

    <div
      v-if="loading"
      class="ot-loading"
      data-testid="member-outcomes-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="ot-empty"
      data-testid="member-outcomes-empty"
    >
      暂无成员结果
    </div>

    <table
      v-else
      class="ot-grid"
      data-testid="member-outcomes-grid"
    >
      <thead>
        <tr>
          <th>member_id</th>
          <th>role</th>
          <th>success</th>
          <th class="num">
            steps
          </th>
          <th class="num">
            tool_calls
          </th>
          <th>final_answer 摘要</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="o in outcomes"
          :key="o.member_id"
          class="ot-row"
          :data-testid="`member-outcome-row-${o.member_id}`"
          :data-success="o.success ? 'true' : 'false'"
          @click="onRowClick(o.member_id)"
        >
          <td class="member-id">
            {{ o.member_id }}
          </td>
          <td class="role">
            {{ o.role }}
          </td>
          <td>
            <span :class="['badge', o.success ? 'badge-ok' : 'badge-fail']">
              {{ o.success ? '✓' : '✗' }}
            </span>
          </td>
          <td class="num">
            {{ o.steps }}
          </td>
          <td class="num">
            {{ o.tool_calls }}
          </td>
          <td class="answer">
            {{ answerSummary(o) || '(无)' }}
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.outcomes-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.ot-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.ot-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.ot-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.ot-empty,
.ot-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.ot-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.ot-grid th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.ot-grid td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.ot-grid .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.ot-row {
  cursor: pointer;
  transition: background 0.15s;
}

.ot-row:hover {
  background: #1e242e;
}

.member-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #10b981;
}

.role {
  color: var(--route-panel-color, #06b6d4);
  font-weight: 600;
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
