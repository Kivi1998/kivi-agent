<script setup lang="ts">
// TeamDashboardDetail：单 team 详情页
// 顶部 team 摘要（goal / member_count / success / time 区间）
// 中部 DelegationTree（成员 → 委派 sub-task → 状态）
// 下部 RoleTimeline + MemberOutcomesTable
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createTeamDashboardApi } from '@/api/team_dashboard'
import type {
  DelegationStep,
  T11Metrics,
  TeamDetail
} from '@/types/api'
import DelegationTree from '@/components/team/DelegationTree.vue'
import RoleTimeline from '@/components/team/RoleTimeline.vue'
import MemberOutcomesTable from '@/components/team/MemberOutcomesTable.vue'

const props = defineProps<{
  teamId: string
}>()

const router = useRouter()

const detail = ref<TeamDetail | null>(null)
const delegations = ref<DelegationStep[]>([])
const metrics = ref<T11Metrics | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const api = createTeamDashboardApi()

/** 加载 team 详情 + delegations + metrics（并行） */
async function loadTeam(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [detailRes, delegationsRes, metricsRes] = await Promise.all([
      api.getTeam(props.teamId),
      api.getTeamDelegations(props.teamId),
      api.getTeamMetrics(props.teamId)
    ])
    detail.value = detailRes
    delegations.value = delegationsRes
    metrics.value = metricsRes
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadTeam()
})

/** goal 截前 100 字 */
const goalShort = computed<string>(() => {
  const g = detail.value?.goal ?? ''
  if (!g) return '—'
  return g.length <= 100 ? g : g.slice(0, 100) + '…'
})

/** 时间区间 "2026-07-23 00:00 → 00:01" */
const timeRange = computed<string>(() => {
  if (!detail.value) return '—'
  const c = detail.value.created_at
  const f = detail.value.finished_at
  if (!c) return '(未开始)'
  if (!f) return `${c} → (进行中)`
  return `${c} → ${f}`
})

/** 6 指标字符串列表（用于展示） */
const metricLines = computed<string[]>(() => {
  const m = metrics.value
  if (!m) return []
  return [
    `team_success_rate: ${(m.team_success_rate.rate * 100).toFixed(1)}% (${m.team_success_rate.passed}/${m.team_success_rate.total})`,
    `delegation_accuracy: ${(m.delegation_accuracy.rate * 100).toFixed(1)}% (${m.delegation_accuracy.matched}/${m.delegation_accuracy.applicable})`,
    `handoff_quality: ${(m.handoff_quality.rate * 100).toFixed(1)}% (${m.handoff_quality.successful}/${m.handoff_quality.total})`,
    `coordination_latency_s: ${m.coordination_latency_s.avg_s.toFixed(2)} (p50=${m.coordination_latency_s.p50_s.toFixed(2)}, p95=${m.coordination_latency_s.p95_s.toFixed(2)})`,
    `agent_utilization: ${(m.agent_utilization.rate * 100).toFixed(1)}% (${m.agent_utilization.tool_calls}/${m.agent_utilization.total_steps})`,
    `role_consistency: ${(m.role_consistency.rate * 100).toFixed(1)}% (changes=${m.role_consistency.role_changes}/${m.role_consistency.total_steps})`
  ]
})

/** 成员结果点击 → 跳 case 详情 */
function onSelectMember(memberId: string): void {
  void router.push({
    name: 'team-case-detail',
    params: { teamId: props.teamId, caseId: memberId }
  })
}

/** 返回 team 总览 */
function onBack(): void {
  void router.push({ name: 'team-dashboard' })
}
</script>

<template>
  <div
    class="team-detail"
    data-testid="team-detail"
  >
    <header class="team-detail-header">
      <button
        class="back-btn"
        data-testid="team-back-btn"
        @click="onBack"
      >
        ← 返回
      </button>
      <h1 class="team-detail-title">
        Team: {{ teamId }}
      </h1>
    </header>

    <section
      v-if="error"
      class="team-detail-error"
      data-testid="team-detail-error"
    >
      {{ error }}
    </section>

    <section
      class="team-summary-grid"
      data-testid="team-detail-summary"
    >
      <div class="summary-tile">
        <div class="tile-label">
          goal
        </div>
        <div
          class="tile-value tile-goal"
          data-testid="team-detail-goal"
        >
          {{ goalShort }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          members
        </div>
        <div
          class="tile-value"
          data-testid="team-detail-member-count"
        >
          {{ detail?.member_count ?? '—' }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          success
        </div>
        <div
          class="tile-value"
          data-testid="team-detail-success"
        >
          {{ detail?.success ? '✓' : '✗' }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          time range
        </div>
        <div
          class="tile-value tile-time"
          data-testid="team-detail-time-range"
        >
          {{ timeRange }}
        </div>
      </div>
    </section>

    <section
      v-if="metricLines.length > 0"
      class="team-metrics"
      data-testid="team-detail-metrics"
    >
      <h3 class="metrics-title">
        6 指标
      </h3>
      <ul class="metrics-list">
        <li
          v-for="(line, i) in metricLines"
          :key="i"
          class="metrics-item"
        >
          {{ line }}
        </li>
      </ul>
    </section>

    <DelegationTree
      :members="detail?.member_outcomes ?? []"
      :steps="delegations"
    />

    <RoleTimeline :members="detail?.member_outcomes ?? []" />

    <MemberOutcomesTable
      :outcomes="detail?.member_outcomes ?? []"
      :loading="loading"
      @select="onSelectMember"
    />
  </div>
</template>

<style scoped>
.team-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.team-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.team-detail-title {
  font-size: 22px;
  font-weight: 700;
  color: #c9d1d9;
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.back-btn {
  background: #1e242e;
  border: 1px solid #2a313c;
  color: #c9d1d9;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
}

.back-btn:hover {
  background: #2a313c;
}

.team-detail-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.team-summary-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 2fr;
  gap: 12px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.summary-tile {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 6px;
}

.tile-label {
  color: var(--muted-color);
  font-size: 12px;
}

.tile-value {
  color: #10b981;
  font-size: 16px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.tile-goal {
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tile-time {
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.team-metrics {
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.metrics-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0 0 8px 0;
}

.metrics-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: #c9d1d9;
}

.metrics-item {
  padding: 4px 8px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
}
</style>
