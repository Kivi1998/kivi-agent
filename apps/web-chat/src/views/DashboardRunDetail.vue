<script setup lang="ts">
// DashboardRunDetail：单 run 详情页
// 顶部 run 摘要（case_count / success_count / started_at）
// 中部 MetricsBar（单 run 7 指标）
// 下部 CaseTable（cases 列表）
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createDashboardApi } from '@/api/dashboard'
import type { CaseEvalResult, MetricsReport, RunDetail } from '@/types/api'
import MetricsBar from '@/components/MetricsBar.vue'
import CaseTable from '@/components/CaseTable.vue'

const props = defineProps<{
  runId: string
}>()

const router = useRouter()

const detail = ref<RunDetail | null>(null)
const metrics = ref<MetricsReport | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const api = createDashboardApi()

/** 加载 run 详情 + 指标（并行） */
async function loadRun(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [detailRes, metricsRes] = await Promise.all([
      api.fetchRunDetail(props.runId),
      api.fetchMetrics(props.runId)
    ])
    detail.value = detailRes
    metrics.value = metricsRes
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadRun()
})

/** 顶部摘要：成功率（保留 1 位小数） */
const successRate = computed<string>(() => {
  if (!detail.value) return '—'
  if (detail.value.case_count === 0) return '0.0%'
  return ((detail.value.success_count / detail.value.case_count) * 100).toFixed(1) + '%'
})

/** 时间戳格式化 */
const startedAt = computed<string>(() => {
  if (!detail.value) return '—'
  // started_at 不在 RunDetail 中；从 metrics.generated_at 兜底
  return metrics.value?.generated_at ?? '—'
})

/** cases 列表（转 CaseEvalResult 数组） */
const cases = computed<CaseEvalResult[]>(() => detail.value?.results ?? [])

/** case 点击 → 跳 case 详情 */
function onSelectCase(caseId: string): void {
  void router.push({
    name: 'dashboard-case-detail',
    params: { runId: props.runId, caseId }
  })
}

/** 返回 dashboard 总览 */
function onBack(): void {
  void router.push({ name: 'dashboard' })
}
</script>

<template>
  <div
    class="run-detail"
    data-testid="run-detail"
  >
    <header class="run-header">
      <button
        class="back-btn"
        data-testid="back-btn"
        @click="onBack"
      >
        ← 返回
      </button>
      <h1 class="run-title">
        Run: {{ runId }}
      </h1>
    </header>

    <section
      v-if="error"
      class="run-error"
      data-testid="run-error"
    >
      {{ error }}
    </section>

    <section
      class="run-summary"
      data-testid="run-summary"
    >
      <div class="summary-tile">
        <div class="tile-label">
          case_count
        </div>
        <div
          class="tile-value"
          data-testid="run-case-count"
        >
          {{ detail?.case_count ?? '—' }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          success_count
        </div>
        <div
          class="tile-value"
          data-testid="run-success-count"
        >
          {{ detail?.success_count ?? '—' }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          成功率
        </div>
        <div
          class="tile-value"
          data-testid="run-success-rate"
        >
          {{ successRate }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          generated_at
        </div>
        <div
          class="tile-value"
          data-testid="run-generated-at"
        >
          {{ startedAt }}
        </div>
      </div>
    </section>

    <MetricsBar
      :metrics="metrics"
      :title="`run ${runId} 7 指标`"
    />

    <CaseTable
      :cases="cases"
      :loading="loading"
      @select="onSelectCase"
    />
  </div>
</template>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.run-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.run-title {
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

.run-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
  color: var(--route-panel-color, #06b6d4);
  font-size: 18px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.run-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
</style>
