<script setup lang="ts">
// CodingSummaryCard：Coding Dashboard 顶部 4 个 metric 大卡
// 展示任务完成率 / 测试通过率 / 平均迭代轮数 / 自恢复率
import { computed } from 'vue'
import type { CodingSummary } from '@/types/api'

const props = defineProps<{
  /** T12 6 指标汇总；null 表示尚未加载 */
  summary: CodingSummary | null
  /** 加载中状态（控制骨架占位） */
  loading?: boolean
}>()

/** 任务完成率百分比 */
const completionPct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.task_completion_rate * 100).toFixed(1) + '%'
})

/** 测试通过率百分比 */
const testsPassedPct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.tests_passed_rate * 100).toFixed(1) + '%'
})

/** 平均迭代轮数（保留 1 位小数） */
const avgIterStr = computed<string>(() => {
  if (!props.summary) return '—'
  return props.summary.avg_iteration_count.toFixed(1)
})

/** 自恢复率百分比 */
const recoveryPct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.self_recovery_rate * 100).toFixed(1) + '%'
})
</script>

<template>
  <section
    class="coding-summary-card"
    data-testid="coding-summary-card"
    :data-loading="loading ? 'true' : 'false'"
  >
    <div
      class="metric-tile"
      data-testid="cmetric-completion"
    >
      <div class="metric-label">
        任务完成率
      </div>
      <div class="metric-value">
        {{ completionPct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="cmetric-tests-passed"
    >
      <div class="metric-label">
        测试通过率
      </div>
      <div class="metric-value">
        {{ testsPassedPct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="cmetric-iterations"
    >
      <div class="metric-label">
        平均迭代
      </div>
      <div class="metric-value">
        {{ avgIterStr }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="cmetric-recovery"
    >
      <div class="metric-label">
        自恢复率
      </div>
      <div class="metric-value">
        {{ recoveryPct }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.coding-summary-card {
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
  color: #d946ef;
  font-size: 24px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
