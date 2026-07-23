<script setup lang="ts">
// CodingDashboard：T12 coding Agent Dashboard 总览
// 顶部 CodingSummaryCard（4 metric 大卡）
// 下部 RunsList（最近 20 个 coding run）
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createCodingDashboardApi } from '@/api/coding_dashboard'
import type { CodingRunItem, CodingSummary } from '@/types/api'
import CodingSummaryCard from '@/components/coding/CodingSummaryCard.vue'
import RunsList from '@/components/coding/RunsList.vue'

const router = useRouter()

const summary = ref<CodingSummary | null>(null)
const runs = ref<CodingRunItem[]>([])
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

/** Coding Dashboard API 客户端 */
const api = createCodingDashboardApi()

/** 加载 coding dashboard 数据（并行：summary + runs） */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [summaryRes, runsRes] = await Promise.all([
      api.getCodingSummary(),
      api.listCodingRuns(20, 0)
    ])
    summary.value = summaryRes
    runs.value = runsRes.runs
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadAll()
})

/** 行点击 → 跳 coding run 详情 */
function onSelectRun(runId: string): void {
  void router.push({ name: 'coding-dashboard-detail', params: { runId } })
}
</script>

<template>
  <div
    class="coding-dashboard"
    data-testid="coding-dashboard-overview"
  >
    <header class="coding-header">
      <h1 class="coding-title">
        Coding Dashboard
      </h1>
      <p class="coding-sub">
        T12 coding Agent 总览（Wave 5.2）
      </p>
    </header>

    <div
      v-if="error"
      class="coding-error"
      data-testid="coding-dashboard-error"
    >
      {{ error }}
    </div>

    <CodingSummaryCard
      :summary="summary"
      :loading="loading"
    />

    <RunsList
      :runs="runs"
      :loading="loading"
      @select="onSelectRun"
    />
  </div>
</template>

<style scoped>
.coding-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.coding-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.coding-title {
  font-size: 22px;
  font-weight: 700;
  color: #c9d1d9;
  margin: 0;
}

.coding-sub {
  font-size: 13px;
  color: var(--muted-color);
  margin: 0;
}

.coding-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
</style>
