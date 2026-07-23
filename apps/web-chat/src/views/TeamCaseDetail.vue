<script setup lang="ts">
// TeamCaseDetail：单成员 / sub-task 详情
// 顶部成员摘要（member_id / role / success / steps / tool_calls）
// 下部 final_answer 完整文本
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createTeamDashboardApi } from '@/api/team_dashboard'
import type { MemberOutcome, TeamDetail } from '@/types/api'

const props = defineProps<{
  teamId: string
  caseId: string
}>()

const router = useRouter()

const detail = ref<TeamDetail | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const api = createTeamDashboardApi()

async function loadCase(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const d = await api.getTeam(props.teamId)
    detail.value = d
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadCase()
})

/** 找到目标 member outcome */
const member = computed<MemberOutcome | null>(() => {
  return detail.value?.member_outcomes.find((m) => m.member_id === props.caseId) ?? null
})

/** 是否找到 */
const notFound = computed<boolean>(() => {
  return !loading.value && !member.value
})

/** final answer 完整文本 */
const finalAnswer = computed<string>(() => {
  return member.value?.final_answer ?? ''
})

function onBack(): void {
  void router.push({
    name: 'team-dashboard-detail',
    params: { teamId: props.teamId }
  })
}
</script>

<template>
  <div
    class="team-case-detail"
    data-testid="team-case-detail"
  >
    <header class="case-header">
      <button
        class="back-btn"
        data-testid="team-case-back-btn"
        @click="onBack"
      >
        ← 返回 Team
      </button>
      <h1 class="case-title">
        Member: {{ caseId }}
      </h1>
    </header>

    <section
      v-if="error"
      class="case-error"
      data-testid="team-case-error"
    >
      {{ error }}
    </section>

    <section
      v-if="notFound"
      class="case-not-found"
      data-testid="team-case-not-found"
    >
      找不到该成员：{{ caseId }}
    </section>

    <template v-else-if="member">
      <section
        class="case-summary"
        data-testid="team-case-summary"
      >
        <div class="summary-tile">
          <div class="tile-label">
            member_id
          </div>
          <div
            class="tile-value"
            data-testid="team-case-member-id"
          >
            {{ member.member_id }}
          </div>
        </div>
        <div class="summary-tile">
          <div class="tile-label">
            role
          </div>
          <div
            class="tile-value"
            data-testid="team-case-role"
          >
            {{ member.role }}
          </div>
        </div>
        <div class="summary-tile">
          <div class="tile-label">
            success
          </div>
          <div
            class="tile-value"
            data-testid="team-case-success"
          >
            {{ member.success ? '✓' : '✗' }}
          </div>
        </div>
        <div class="summary-tile">
          <div class="tile-label">
            steps
          </div>
          <div
            class="tile-value"
            data-testid="team-case-steps"
          >
            {{ member.steps }}
          </div>
        </div>
        <div class="summary-tile">
          <div class="tile-label">
            tool_calls
          </div>
          <div
            class="tile-value"
            data-testid="team-case-tool-calls"
          >
            {{ member.tool_calls }}
          </div>
        </div>
        <div class="summary-tile">
          <div class="tile-label">
            finished_at
          </div>
          <div
            class="tile-value"
            data-testid="team-case-finished-at"
          >
            {{ member.finished_at ?? '(进行中)' }}
          </div>
        </div>
      </section>

      <section
        class="case-final"
        data-testid="team-case-final"
      >
        <h3 class="final-title">
          final_answer
        </h3>
        <pre
          class="final-pre"
          data-testid="team-case-final-pre"
        >{{ finalAnswer || '(无)' }}</pre>
      </section>
    </template>
  </div>
</template>

<style scoped>
.team-case-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

.case-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.case-title {
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

.case-error,
.case-not-found {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.case-summary {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
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

.case-final {
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.final-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0 0 8px 0;
}

.final-pre {
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  color: #c9d1d9;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
