<script setup lang="ts">
// TeamDashboard：T11 多 Agent 协作 Dashboard 总览
// 顶部 TeamSummaryCard（4 metric 大卡）
// 下部 TeamsList（最近 20 个 team 计划）
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createTeamDashboardApi } from '@/api/team_dashboard'
import type { TeamSummary, TeamSummaryItem } from '@/types/api'
import TeamSummaryCard from '@/components/team/TeamSummaryCard.vue'
import TeamsList from '@/components/team/TeamsList.vue'

const router = useRouter()

const summary = ref<TeamSummary | null>(null)
const teams = ref<TeamSummaryItem[]>([])
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

/** Team Dashboard API 客户端：默认走 vite proxy，测试可注入 */
const api = createTeamDashboardApi()

/** 加载 team dashboard 数据（并行：summary + teams） */
async function loadAll(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [summaryRes, teamsRes] = await Promise.all([
      api.getTeamSummary(),
      api.listTeams(20, 0)
    ])
    summary.value = summaryRes
    teams.value = teamsRes.teams
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadAll()
})

/** 行点击 → 跳 team 详情 */
function onSelectTeam(teamId: string): void {
  void router.push({ name: 'team-dashboard-detail', params: { teamId } })
}
</script>

<template>
  <div
    class="team-dashboard"
    data-testid="team-dashboard-overview"
  >
    <header class="team-header">
      <h1 class="team-title">
        Team Dashboard
      </h1>
      <p class="team-sub">
        T11 多 Agent 协作总览（Wave 5.2）
      </p>
    </header>

    <div
      v-if="error"
      class="team-error"
      data-testid="team-dashboard-error"
    >
      {{ error }}
    </div>

    <TeamSummaryCard
      :summary="summary"
      :loading="loading"
    />

    <TeamsList
      :teams="teams"
      :loading="loading"
      @select="onSelectTeam"
    />
  </div>
</template>

<style scoped>
.team-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.team-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.team-title {
  font-size: 22px;
  font-weight: 700;
  color: #c9d1d9;
  margin: 0;
}

.team-sub {
  font-size: 13px;
  color: var(--muted-color);
  margin: 0;
}

.team-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
</style>
