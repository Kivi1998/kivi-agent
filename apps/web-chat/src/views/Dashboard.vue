<script setup lang="ts">
// Dashboard：总览页
// 顶部 SummaryCard（4 个 metric 大卡）
// 中部 MetricsBar（汇总 7 指标）
// 下部 RunsList（最近 20 个 run）
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  createDashboardApi,
  computeSummaryFromCases
} from '@/api/dashboard'
import type {
  CaseEvalResult,
  MetricsReport,
  RunSummary,
  Summary
} from '@/types/api'
import SummaryCard from '@/components/SummaryCard.vue'
import MetricsBar from '@/components/MetricsBar.vue'
import RunsList from '@/components/RunsList.vue'

const router = useRouter()

const summary = ref<Summary | null>(null)
const runs = ref<RunSummary[]>([])
const summaryMetrics = ref<MetricsReport | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

/** Dashboard API 客户端：默认走 vite proxy，测试可注入 */
const api = createDashboardApi()

/** 加载全部 dashboard 数据（并行：summary + runs + 前端汇总 metrics） */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [summaryRes, runsRes] = await Promise.all([
      api.fetchSummary(),
      api.fetchRuns(20, 0)
    ])
    summary.value = summaryRes
    runs.value = runsRes.runs

    // 尝试拉最近 1 个 run 的 metrics 作为汇总（前端 fallback：用 cases 再算一次）
    const recent = runsRes.runs[0]
    if (recent) {
      try {
        const detail = await api.fetchRunDetail(recent.run_id)
        const results: CaseEvalResult[] = detail.results
        const localSummary = computeSummaryFromCases(results)
        // 用本地 summary 补一份 metrics（mock：用同源数据生成 7 指标结构）
        summaryMetrics.value = buildMetricsFromSummary(localSummary, recent.run_id)
      } catch {
        // 拉取失败时用空 metrics（MetricsBar 会显示 empty state）
        summaryMetrics.value = null
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

/** 用本地算出的 Summary 拼一份 MetricsReport（供 MetricsBar 复用） */
function buildMetricsFromSummary(s: Summary, datasetName: string): MetricsReport {
  return {
    dataset_name: datasetName,
    case_count: s.case_count,
    generated_at: new Date().toISOString(),
    metrics: {
      task_success_rate: {
        rate: s.success_rate,
        passed: Math.round(s.case_count * s.success_rate),
        total: s.case_count
      },
      route_accuracy: { rate: 0, matched: 0, applicable: 0 },
      tool_selection_accuracy: {
        exact_match_rate: 0,
        contain_match_rate: 0,
        applicable: 0
      },
      rag_citation_accuracy: { rate: 0, matched: 0, applicable: 0 },
      avg_latency_seconds: {
        avg_s: s.avg_latency_s,
        p50_s: s.avg_latency_s,
        p95_s: s.avg_latency_s,
        count: s.case_count
      },
      total_tokens: {
        input: Math.round(s.total_tokens * 0.3),
        output: Math.round(s.total_tokens * 0.7),
        cache_read: 0,
        total: s.total_tokens
      },
      total_cost_usd: {
        total_usd: s.total_cost_usd,
        model: 'unknown',
        per_case_avg_usd: s.case_count > 0 ? s.total_cost_usd / s.case_count : 0
      }
    }
  }
}

onMounted(() => {
  void loadAll()
})

/** 行点击 → 跳 run 详情 */
function onSelectRun(runId: string): void {
  void router.push({ name: 'dashboard-run-detail', params: { runId } })
}
</script>

<template>
  <div
    class="dashboard"
    data-testid="dashboard-overview"
  >
    <header class="dashboard-header">
      <h1 class="dashboard-title">
        Trace Dashboard
      </h1>
      <p class="dashboard-sub">
        评测运行总览（Wave 5.1）
      </p>
    </header>

    <div
      v-if="error"
      class="dashboard-error"
      data-testid="dashboard-error"
    >
      {{ error }}
    </div>

    <SummaryCard
      :summary="summary"
      :loading="loading"
    />

    <MetricsBar
      :metrics="summaryMetrics"
      title="最近 run 指标汇总"
    />

    <RunsList
      :runs="runs"
      :loading="loading"
      @select="onSelectRun"
    />
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.dashboard-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dashboard-title {
  font-size: 22px;
  font-weight: 700;
  color: #c9d1d9;
  margin: 0;
}

.dashboard-sub {
  font-size: 13px;
  color: var(--muted-color);
  margin: 0;
}

.dashboard-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
</style>
