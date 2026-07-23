<script setup lang="ts">
// SummaryCard：Dashboard 顶部 4 个 metric 大卡
// 展示成功率 / 平均延迟 / 总 Token / 总成本
import { computed } from 'vue'
import type { Summary } from '@/types/api'

const props = defineProps<{
  /** 汇总数据；null 表示尚未加载 */
  summary: Summary | null
  /** 加载中状态（控制骨架占位） */
  loading?: boolean
}>()

/** 成功率百分比（0-100，保留 1 位小数） */
const successRatePct = computed<string>(() => {
  if (!props.summary) return '—'
  return (props.summary.success_rate * 100).toFixed(1) + '%'
})

/** 平均延迟（秒，保留 2 位小数） */
const avgLatencyStr = computed<string>(() => {
  if (!props.summary) return '—'
  return props.summary.avg_latency_s.toFixed(2) + 's'
})

/** 总 token 千分位 */
const totalTokensStr = computed<string>(() => {
  if (!props.summary) return '—'
  return props.summary.total_tokens.toLocaleString('en-US')
})

/** 总成本美元（保留 4 位小数） */
const totalCostStr = computed<string>(() => {
  if (!props.summary) return '—'
  return '$' + props.summary.total_cost_usd.toFixed(4)
})
</script>

<template>
  <section
    class="summary-card"
    data-testid="summary-card"
    :data-loading="loading ? 'true' : 'false'"
  >
    <div
      class="metric-tile"
      data-testid="metric-success-rate"
    >
      <div class="metric-label">
        成功率
      </div>
      <div class="metric-value">
        {{ successRatePct }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="metric-avg-latency"
    >
      <div class="metric-label">
        平均延迟
      </div>
      <div class="metric-value">
        {{ avgLatencyStr }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="metric-total-tokens"
    >
      <div class="metric-label">
        总 Token
      </div>
      <div class="metric-value">
        {{ totalTokensStr }}
      </div>
    </div>
    <div
      class="metric-tile"
      data-testid="metric-total-cost"
    >
      <div class="metric-label">
        总成本
      </div>
      <div class="metric-value">
        {{ totalCostStr }}
      </div>
    </div>
  </section>
</template>

<style scoped>
.summary-card {
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
  color: var(--route-panel-color, #06b6d4);
  font-size: 24px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
