<script setup lang="ts">
// RoleTimeline：成员角色时间线
// 每个 member 渲染一行；按 created_at / finished_at 划区间
// 成员列：member_id / role / 时间区间 / 步数
import { computed } from 'vue'
import type { MemberOutcome } from '@/types/api'

const props = defineProps<{
  members: MemberOutcome[]
  /** team 起始时间（用于对齐 x 轴） */
  teamStart?: string | null
}>()

/** 时间戳格式化为本地可读字符串（HH:mm:ss） */
function formatTime(ts: string | null): string {
  if (!ts) return '(进行中)'
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

/** 区间字符串 "10:00:00 → 10:01:30" */
function interval(m: MemberOutcome): string {
  return `${formatTime(m.finished_at)}`
}

/** 按 member_id 字母序稳定排序 */
const sorted = computed<MemberOutcome[]>(() => {
  return [...props.members].sort((a, b) => a.member_id.localeCompare(b.member_id))
})
</script>

<template>
  <section
    class="role-timeline"
    data-testid="role-timeline"
  >
    <header class="rt-header">
      <h3 class="rt-title">
        成员角色时间线
      </h3>
      <span
        v-if="members.length > 0"
        class="rt-count"
        data-testid="role-timeline-count"
      >{{ members.length }} 成员</span>
    </header>

    <div
      v-if="members.length === 0"
      class="rt-empty"
      data-testid="role-timeline-empty"
    >
      暂无成员
    </div>

    <table
      v-else
      class="rt-table"
      data-testid="role-timeline-table"
    >
      <thead>
        <tr>
          <th>member_id</th>
          <th>role</th>
          <th class="num">
            steps
          </th>
          <th class="num">
            tool_calls
          </th>
          <th>finished_at</th>
          <th>success</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="m in sorted"
          :key="m.member_id"
          class="rt-row"
          :data-testid="`role-timeline-row-${m.member_id}`"
          :data-success="m.success ? 'true' : 'false'"
        >
          <td class="member-id">
            {{ m.member_id }}
          </td>
          <td class="role-name">
            {{ m.role }}
          </td>
          <td class="num">
            {{ m.steps }}
          </td>
          <td class="num">
            {{ m.tool_calls }}
          </td>
          <td>{{ interval(m) }}</td>
          <td>
            <span :class="['badge', m.success ? 'badge-ok' : 'badge-fail']">
              {{ m.success ? '✓' : '✗' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.role-timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.rt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.rt-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.rt-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.rt-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.rt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.rt-table th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid #1e242e;
  color: var(--muted-color);
  font-weight: 500;
  font-size: 12px;
}

.rt-table td {
  padding: 8px;
  border-bottom: 1px solid #1e242e;
  color: #c9d1d9;
}

.rt-table .num {
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.member-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #10b981;
}

.role-name {
  color: var(--route-panel-color, #06b6d4);
  font-weight: 600;
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
