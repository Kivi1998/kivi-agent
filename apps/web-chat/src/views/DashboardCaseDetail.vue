<script setup lang="ts">
// DashboardCaseDetail：单 case 详情页
// 主体 TraceTimeline（单 case 事件流）
// 右侧 RAG 引用列表 + 工具调用列表
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { createDashboardApi } from '@/api/dashboard'
import type { TraceTimeline as TraceTimelineT } from '@/types/api'
import TraceTimeline from '@/components/TraceTimeline.vue'

const props = defineProps<{
  runId: string
  caseId: string
}>()

const router = useRouter()

const trace = ref<TraceTimelineT | null>(null)
const loading = ref<boolean>(false)
const error = ref<string | null>(null)

const api = createDashboardApi()

/** 加载单 case 事件流 */
async function loadTrace(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const res = await api.fetchTraces(props.runId, props.caseId)
    // 后端返回 run 维度的 traces[]；本视图只显示对应 case
    trace.value = res.traces.find((t) => t.case_id === props.caseId) ?? null
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadTrace()
})

/** 当前 case 的 tool_calls */
const toolCalls = computed(() => trace.value?.tool_calls ?? [])

/** 当前 case 的 RAG 引用 */
const ragSources = computed(() => trace.value?.rag_sources ?? [])

/** 工具调用时间（毫秒） */
function durationMs(start: string, end: string | null): string {
  if (!end) return '进行中'
  const s = new Date(start).getTime()
  const e = new Date(end).getTime()
  if (Number.isNaN(s) || Number.isNaN(e)) return '—'
  return (e - s).toString() + 'ms'
}

/** 返回 run 详情 */
function onBack(): void {
  void router.push({
    name: 'dashboard-run-detail',
    params: { runId: props.runId }
  })
}
</script>

<template>
  <div
    class="case-detail"
    data-testid="case-detail"
  >
    <header class="case-header">
      <button
        class="back-btn"
        data-testid="back-btn"
        @click="onBack"
      >
        ← 返回 Run
      </button>
      <h1 class="case-title">
        Case: {{ caseId }}
      </h1>
      <span class="run-label">run: {{ runId }}</span>
    </header>

    <div
      v-if="error"
      class="case-error"
      data-testid="case-error"
    >
      {{ error }}
    </div>

    <div
      v-if="loading"
      class="case-loading"
      data-testid="case-loading"
    >
      加载中...
    </div>

    <div
      v-else-if="!trace"
      class="case-empty"
      data-testid="case-empty"
    >
      未找到该 case 的事件流
    </div>

    <div
      v-else
      class="case-body"
    >
      <div class="case-main">
        <TraceTimeline
          :trace="trace"
          :case-id="caseId"
        />
      </div>
      <aside
        class="case-side"
        data-testid="case-side"
      >
        <section
          class="side-block"
          data-testid="side-tools"
        >
          <h3 class="side-title">
            工具调用 ({{ toolCalls.length }})
          </h3>
          <div
            v-if="toolCalls.length === 0"
            class="side-empty"
          >
            无
          </div>
          <ul
            v-else
            class="side-list"
          >
            <li
              v-for="(t, i) in toolCalls"
              :key="i"
              :data-testid="`side-tool-${t.tool_name}`"
              class="side-row"
            >
              <span class="side-row-name">{{ t.tool_name }}</span>
              <span
                class="side-row-status"
                :data-success="t.success"
              >{{ t.success ? '✓' : '✗' }}</span>
              <span class="side-row-meta">{{ durationMs(t.started_at, t.finished_at) }}</span>
            </li>
          </ul>
        </section>

        <section
          class="side-block"
          data-testid="side-rag"
        >
          <h3 class="side-title">
            RAG 引用 ({{ ragSources.length }})
          </h3>
          <div
            v-if="ragSources.length === 0"
            class="side-empty"
          >
            无
          </div>
          <ul
            v-else
            class="side-list"
          >
            <li
              v-for="(s, i) in ragSources"
              :key="i"
              :data-testid="`side-rag-${i}`"
              class="side-row"
            >
              <span class="side-row-name">{{ String(s.id ?? s.title ?? 'src-' + i) }}</span>
            </li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.case-detail {
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

.run-label {
  font-size: 12px;
  color: var(--muted-color);
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

.case-error {
  background: #7f1d1d;
  color: #fecaca;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.case-loading,
.case-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 30px 0;
  font-size: 13px;
}

.case-body {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
  align-items: start;
}

.case-main {
  min-width: 0;
}

.case-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.side-block {
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.side-title {
  font-size: 13px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0 0 8px;
}

.side-empty {
  font-size: 12px;
  color: var(--muted-color);
  text-align: center;
  padding: 10px 0;
}

.side-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.side-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  font-size: 12px;
}

.side-row-name {
  flex: 1;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--route-panel-color, #06b6d4);
  word-break: break-all;
}

.side-row-status {
  color: #10b981;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.side-row-status[data-success='false'] {
  color: #ef4444;
}

.side-row-meta {
  color: var(--muted-color);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
