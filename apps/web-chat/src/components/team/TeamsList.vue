<script setup lang="ts">
// TeamsList：team 计划列表（按创建时间倒序）
// 表格列：team_id / goal / member_count / success / created_at
// 点击行 → emit('select', teamId)
import { computed } from 'vue'
import type { TeamSummaryItem } from '@/types/api'

const props = defineProps<{
  teams: TeamSummaryItem[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', teamId: string): void
}>()

/** 列表为空 */
const isEmpty = computed<boolean>(() => props.teams.length === 0)

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

/** goal 截断为前 60 字 */
function goalShort(goal: string): string {
  if (goal.length <= 60) return goal
  return goal.slice(0, 60) + '…'
}

/** 行点击 → 通知上层跳转 */
function onRowClick(teamId: string): void {
  emit('select', teamId)
}
</script>

<template>
  <section
    class="teams-list"
    data-testid="teams-list"
  >
    <header class="teams-header">
      <h3 class="teams-title">
        Team 计划
      </h3>
      <span
        v-if="!loading && !isEmpty"
        class="teams-count"
        data-testid="teams-count"
      >共 {{ teams.length }} 条</span>
    </header>

    <div
      v-if="loading"
      class="teams-loading"
      data-testid="teams-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="isEmpty"
      class="teams-empty"
      data-testid="teams-empty"
    >
      暂无 team 计划
    </div>

    <table
      v-else
      class="teams-table"
      data-testid="teams-table"
    >
      <thead>
        <tr>
          <th>team_id</th>
          <th>goal</th>
          <th class="num">
            members
          </th>
          <th>success</th>
          <th>created_at</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="t in teams"
          :key="t.team_id"
          :data-testid="`teams-row-${t.team_id}`"
          :data-success="t.success ? 'true' : 'false'"
          class="teams-row"
          @click="onRowClick(t.team_id)"
        >
          <td class="team-id">
            {{ t.team_id }}
          </td>
          <td class="goal">
            {{ goalShort(t.goal) }}
          </td>
          <td class="num">
            {{ t.member_count }}
          </td>
          <td>
            <span :class="['badge', t.success ? 'badge-ok' : 'badge-fail']">
              {{ t.success ? '✓' : '✗' }}
            </span>
          </td>
          <td>{{ formatTime(t.created_at) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.teams-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.teams-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.teams-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.teams-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.teams-empty,
.teams-loading {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.teams-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.teams-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.teams-table td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.teams-table .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.teams-row {
  cursor: pointer;
  transition: background 0.15s;
}

.teams-row:hover {
  background: #1e242e;
}

.team-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #10b981;
}

.goal {
  max-width: 320px;
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
