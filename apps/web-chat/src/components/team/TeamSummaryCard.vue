<script setup lang="ts">
// TeamSummaryCard：Team Dashboard 顶部 4 个 metric 大卡
// 展示成功率 / 平均委派精度 / 平均接力质量 / 平均协调延迟
import { computed } from 'vue'
import type { TeamSummary } from '@/types/api'

const props = defineProps<{
  /** T11 6 指标汇总；null 表示尚未加载 */
  summary: TeamSummary | null
  /** 加载中状态（控制骨架占位） */
  loading?: boolean
}>()

/** 成功率百分比（0-100，保留 1 位小数） */
const successRatePct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.success_rate * 100).toFixed(1) + '%'
})

/** 平均委派精度百分比 */
const delegationPct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.avg_delegation_accuracy * 100).toFixed(1) + '%'
})

/** 平均接力质量百分比 */
const handoffPct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.avg_handoff_quality * 100).toFixed(1) + '%'
})

/** 平均协调延迟（秒，保留 2 位小数） */
const coordLatencyStr = computed<string>(() => {
  if (!props.summary) return '—'
  return props.summary.avg_coordination_latency_s.toFixed(2) + 's'
})
</script>

<template>
  <section
    class="team-summary-card"
    data-testid="team-summary-card"
    :data-loading="loading ? 'true' : 'false'"
  >
    <div
      class="metric-tile"
      data-testid="tmetric-success-rate"
    >
      <div class="metric-label">
        团队成功率
      </div>
      <div class="metric-value">
        {{ successRatePct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="tmetric-delegation"
    >
      <div class="metric-label">
        委派精度
      </div>
      <div class="metric-value">
        {{ delegationPct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="tmetric-handoff"
    >
      <div class="metric-label">
        接力质量
      </div>
      <div class="metric-value">
        {{ handoffPct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="tmetric-latency"
    >
      <div class="metric-label">
        协调延迟
      </div>
      <div class="metric-value">
        {{ coordLatencyStr }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.team-summary-card {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.metric-tile {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 6px;
}

.metric-label {
  color: var(--muted-color);
  font-size: 12px;
  font-weight: 500;
}

.metric-value {
  color: #10b981;
  font-size: 24px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
