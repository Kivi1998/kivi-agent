<script setup lang="ts">
// TraceTimeline：单 case 事件流时间轴
// 不同事件类型用不同颜色 + 图标：
//   route.decided    🧭 cyan
//   tool.call_started 🔧 yellow
//   rag.sources_cited 📚 blue
//   chart.rendered   📊 magenta
//   run.finished     ✅ green / ❌ red
//   llm.thinking     💭 gray
//   run.started      ▶ green
import { computed } from 'vue'
import type { TraceTimeline } from '@/types/api'

const props = defineProps<{
  /** 单 case 事件流；null 时显示 empty state */
  trace: TraceTimeline | null
  /** case_id（标题展示用） */
  caseId?: string
}>()

/** 事件视觉样式映射：颜色 + 图标 */
const EVENT_STYLE: Record<string, { color: string; icon: string; label: string }> = {
  'route.decided': { color: '#06b6d4', icon: '🧭', label: '路由决策' },
  'tool.call_started': { color: '#eab308', icon: '🔧', label: '工具调用开始' },
  'tool.call_finished': { color: '#eab308', icon: '🔧', label: '工具调用完成' },
  'rag.sources_cited': { color: '#3b82f6', icon: '📚', label: 'RAG 引用' },
  'chart.rendered': { color: '#d946ef', icon: '📊', label: '图表渲染' },
  'llm.thinking': { color: '#9ca3af', icon: '💭', label: 'LLM 思考' },
  'run.started': { color: '#10b981', icon: '▶', label: 'Run 开始' },
  'run.finished': { color: '#10b981', icon: '✅', label: 'Run 成功' },
  'run.failed': { color: '#ef4444', icon: '❌', label: 'Run 失败' }
}

interface EventRow {
  type: string
  ts: string
  color: string
  icon: string
  label: string
  data: Record<string, unknown>
  /** 用于模板 data-testid */
  testKey: string
}

/** 把事件流 + 工具调用 + rag 引用合并成统一时间轴（按 ts 升序） */
const rows = computed<EventRow[]>(() => {
  if (!props.trace) return []
  const list: EventRow[] = []

  // 原始 events
  for (const e of props.trace.events) {
    const style = EVENT_STYLE[e.type] ?? { color: '#6b7280', icon: '·', label: e.type }
    list.push({
      type: e.type,
      ts: e.ts,
      color: style.color,
      icon: style.icon,
      label: style.label,
      data: e.data,
      testKey: `event-${e.type}-${e.ts}`
    })
  }

  // tool_calls 折叠成 tool.call_started 行
  for (const tc of props.trace.tool_calls) {
    list.push({
      type: 'tool.call_started',
      ts: tc.started_at,
      color: tc.success ? '#eab308' : '#ef4444',
      icon: tc.success ? '🔧' : '❌',
      label: `工具 ${tc.tool_name}`,
      data: { success: tc.success, finished_at: tc.finished_at },
      testKey: `tool-${tc.tool_name}-${tc.started_at}`
    })
  }

  // rag_sources 折叠成单行 rag.sources_cited
  if (props.trace.rag_sources.length > 0) {
    list.push({
      type: 'rag.sources_cited',
      ts: list[0]?.ts ?? new Date().toISOString(),
      color: '#3b82f6',
      icon: '📚',
      label: `RAG 引用 ${props.trace.rag_sources.length} 条`,
      data: { count: props.trace.rag_sources.length },
      testKey: `rag-sources-${props.trace.rag_sources.length}`
    })
  }

  // 按 ts 升序
  list.sort((a, b) => a.ts.localeCompare(b.ts))
  return list
})

/** 格式化时间戳 */
function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

/** 把 data 字典转成单行摘要 */
function summarize(data: Record<string, unknown>): string {
  const keys = Object.keys(data)
  if (keys.length === 0) return ''
  return keys
    .slice(0, 3)
    .map((k) => `${k}=${String(data[k]).slice(0, 40)}`)
    .join(' · ')
}
</script>

<template>
  <section
    class="trace-timeline"
    data-testid="trace-timeline"
  >
    <header
      v-if="caseId"
      class="trace-header"
    >
      <span class="trace-title">事件流</span>
      <span
        class="trace-case-id"
        :data-testid="'trace-case-id'"
      >case: {{ caseId }}</span>
    </header>

    <div
      v-if="!trace"
      class="trace-empty"
      data-testid="trace-empty"
    >
      暂无事件
    </div>

    <ol
      v-else
      class="trace-list"
      data-testid="trace-list"
    >
      <li
        v-for="row in rows"
        :key="row.testKey"
        class="trace-item"
        :style="{ borderLeftColor: row.color }"
        :data-event-type="row.type"
        :data-testid="`trace-item-${row.type}`"
      >
        <span
          class="trace-icon"
          :style="{ color: row.color }"
        >{{ row.icon }}</span>
        <div class="trace-body">
          <div class="trace-row">
            <span
              class="trace-label"
              :style="{ color: row.color }"
            >{{ row.label }}</span>
            <span class="trace-time">{{ formatTime(row.ts) }}</span>
          </div>
          <div
            v-if="summarize(row.data)"
            class="trace-data"
          >
            {{ summarize(row.data) }}
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.trace-timeline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.trace-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
}

.trace-case-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--route-panel-color, #06b6d4);
}

.trace-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 30px 0;
  font-size: 13px;
}

.trace-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.trace-item {
  display: flex;
  gap: 10px;
  padding: 8px 10px;
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-left-width: 3px;
  border-radius: 4px;
}

.trace-icon {
  font-size: 18px;
  line-height: 1;
  flex-shrink: 0;
}

.trace-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.trace-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}

.trace-label {
  font-size: 13px;
  font-weight: 600;
}

.trace-time {
  font-size: 11px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: nowrap;
}

.trace-data {
  font-size: 12px;
  color: #c9d1d9;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  word-break: break-all;
}
</style>
