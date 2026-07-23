<script setup lang="ts">
// CodingDashboardDetail：单 coding run 详情页
// 顶部 run 摘要（task / test_file / iteration / success / time 区间）
// 中部 PatchDiffViewer（unified diff 切换）
// 下部 TestHistoryTimeline（pytest 迭代历史）
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createCodingDashboardApi } from '@/api/coding_dashboard'
import type { CodingDetail, T12Metrics } from '@/types/api'
import PatchDiffViewer from '@/components/coding/PatchDiffViewer.vue'
import TestHistoryTimeline from '@/components/coding/TestHistoryTimeline.vue'
import IterationCountBadge from '@/components/coding/IterationCountBadge.vue'

const props = defineProps<{
  runId: string
}>()

const router = useRouter()

const detail = ref<CodingDetail | null>(null)
const metrics = ref<T12Metrics | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const api = createCodingDashboardApi()

/** 加载 coding run 详情 + metrics（并行） */
async function loadRun(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [detailRes, metricsRes] = await Promise.all([
      api.getCodingRun(props.runId),
      api.getCodingMetrics(props.runId)
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

/** task 截前 100 字 */
const taskShort = computed<string>(() => {
  const t = detail.value?.task ?? ''
  if (!t) return '—'
  return t.length <= 100 ? t : t.slice(0, 100) + '…'
})

/** 时间区间 */
const timeRange = computed<string>(() => {
  if (!detail.value) return '—'
  const s = detail.value.started_at
  const f = detail.value.finished_at
  if (!s) return '(未开始)'
  if (!f) return `${s} → (进行中)`
  return `${s} → ${f}`
})

/** iteration_count（用于 badge） */
const iterCount = computed<number>(() => {
  return detail.value?.iteration_count ?? 0
})

/** 8 指标字符串列表 */
const metricLines = computed<string[]>(() => {
  const m = metrics.value
  if (!m) return []
  return [
    `task_completion_rate: ${(m.task_completion_rate.rate * 100).toFixed(1)}% (${m.task_completion_rate.passed}/${m.task_completion_rate.total})`,
    `tests_passed_rate: ${(m.tests_passed_rate.rate * 100).toFixed(1)}% (${m.tests_passed_rate.passed}/${m.tests_passed_rate.total})`,
    `patch_quality: ${(m.patch_quality.rate * 100).toFixed(1)}% (${m.patch_quality.hunks_applied}/${m.patch_quality.hunks_proposed})`,
    `iteration_count: ${m.iteration_count.value}`,
    `time_to_first_pass_s: ${m.time_to_first_pass_s.avg_s.toFixed(2)} (first_pass=${m.time_to_first_pass_s.first_pass_iterations})`,
    `self_recovery_rate: ${(m.self_recovery_rate.rate * 100).toFixed(1)}% (${m.self_recovery_rate.auto_recovered}/${m.self_recovery_rate.total_failures})`,
    `compile_success_rate: ${(m.compile_success_rate.rate * 100).toFixed(1)}% (${m.compile_success_rate.compile_passed}/${m.compile_success_rate.total_runs})`,
    `test_growth_rate: ${(m.test_growth_rate.rate * 100).toFixed(1)}% (${m.test_growth_rate.tests_added}/${m.test_growth_rate.iterations})`
  ]
})

/** 返回 coding 总览 */
function onBack(): void {
  void router.push({ name: 'coding-dashboard' })
}
</script>

<template>
  <div
    class="coding-detail"
    data-testid="coding-detail"
  >
    <header class="coding-detail-header">
      <button
        class="back-btn"
        data-testid="coding-back-btn"
        @click="onBack"
      >
        ← 返回
      </button>
      <h1 class="coding-detail-title">
        Run: {{ runId }}
      </h1>
    </header>

    <section
      v-if="error"
      class="coding-detail-error"
      data-testid="coding-detail-error"
    >
      {{ error }}
    </section>

    <section
      class="coding-summary-grid"
      data-testid="coding-detail-summary"
    >
      <div class="summary-tile summary-tile-wide">
        <div class="tile-label">
          task
        </div>
        <div
          class="tile-value tile-task"
          data-testid="coding-detail-task"
        >
          {{ taskShort }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          test_file
        </div>
        <div
          class="tile-value tile-test-file"
          data-testid="coding-detail-test-file"
        >
          {{ detail?.test_file ?? '—' }}
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          iterations
        </div>
        <div
          class="tile-value"
          data-testid="coding-detail-iterations"
        >
          <IterationCountBadge :iterations="iterCount" />
        </div>
      </div>
      <div class="summary-tile">
        <div class="tile-label">
          success
        </div>
        <div
          class="tile-value"
          data-testid="coding-detail-success"
        >
          {{ detail?.success ? '✓' : '✗' }}
        </div>
      </div>
      <div class="summary-tile summary-tile-wide">
        <div class="tile-label">
          time range
        </div>
        <div
          class="tile-value tile-time"
          data-testid="coding-detail-time-range"
        >
          {{ timeRange }}
        </div>
      </div>
    </section>

    <section
      v-if="metricLines.length > 0"
      class="coding-metrics"
      data-testid="coding-detail-metrics"
    >
      <h3 class="metrics-title">
        8 指标
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

    <PatchDiffViewer :patches="detail?.patches ?? []" />

    <TestHistoryTimeline :records="detail?.test_runs ?? []" />
  </div>
</template>

<style scoped>
.coding-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.coding-detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.coding-detail-title {
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

.coding-detail-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.coding-summary-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr 2fr;
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
  color: #d946ef;
  font-size: 16px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.tile-task {
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tile-test-file {
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tile-time {
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.coding-metrics {
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
