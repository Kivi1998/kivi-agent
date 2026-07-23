<script setup lang="ts">
import { ref } from 'vue'
import type { RagSourcesCitedEvent, RagSource } from '../types/api'

/**
 * CitationWidget — RAG 引用展示组件。
 *
 * 对应 TUI `src/kivi_agent/tui/citation_widget.py`：cyan 卡片 + 引用计数 header
 * + 每条 source 一行。Web 版扩展：每条可点击展开，完整展示 source dict。
 *
 * Props:
 *   event - RagSourcesCitedEvent（来自 rag.sources_cited 事件）
 */
defineProps<{
  event: RagSourcesCitedEvent
}>()

// 展开状态：按 source 在数组中的下标（稳定 id）记录
const expanded = ref<Set<number>>(new Set())

function toggle(idx: number): void {
  // 用新的 Set 触发响应式更新（直接 .add / .delete 不触发 ref 重渲）
  const next = new Set(expanded.value)
  if (next.has(idx)) {
    next.delete(idx)
  } else {
    next.add(idx)
  }
  expanded.value = next
}

function isExpanded(idx: number): boolean {
  return expanded.value.has(idx)
}

// 优先 title，其次 id；用于折叠态显示主标识
function sourceLabel(src: RagSource): string {
  if (src.title) return String(src.title)
  if (src.id) return String(src.id)
  return JSON.stringify(src)
}

// 把 score 格式化为 2 位小数；缺失时退化为 "—"
function formatScore(score: number | undefined): string {
  if (typeof score !== 'number') return '—'
  return score.toFixed(2)
}
</script>

<template>
  <section
    class="citation-widget"
    data-testid="citation-widget"
    :data-run-id="event.run_id"
    :data-source-count="event.sources.length"
  >
    <header class="citation-header">
      <span
        class="citation-icon"
        aria-hidden="true"
      >📚</span>
      <span class="citation-title">引用 ({{ event.sources.length }} 条)</span>
      <span class="citation-run-id">run_id={{ event.run_id }}</span>
    </header>

    <ul
      v-if="event.sources.length > 0"
      class="citation-list"
    >
      <li
        v-for="(src, idx) in event.sources"
        :key="idx"
        class="citation-item"
        :data-testid="`citation-source-${idx}`"
      >
        <button
          type="button"
          class="citation-row"
          :aria-expanded="isExpanded(idx)"
          @click="toggle(idx)"
        >
          <span class="citation-index">[{{ idx + 1 }}]</span>
          <span class="citation-label">{{ sourceLabel(src) }}</span>
          <span class="citation-score">score={{ formatScore(src.score) }}</span>
          <span
            class="citation-toggle"
            aria-hidden="true"
          >{{ isExpanded(idx) ? '▾' : '▸' }}</span>
        </button>
        <div
          v-if="isExpanded(idx)"
          class="citation-detail"
          :data-testid="`citation-detail-${idx}`"
        >
          <div
            v-if="src.id"
            class="detail-row"
          >
            <span class="detail-key">id:</span>
            <span class="detail-value">{{ src.id }}</span>
          </div>
          <div
            v-if="src.title"
            class="detail-row"
          >
            <span class="detail-key">title:</span>
            <span class="detail-value">{{ src.title }}</span>
          </div>
          <div
            v-if="typeof src.score === 'number'"
            class="detail-row"
          >
            <span class="detail-key">score:</span>
            <span class="detail-value">{{ formatScore(src.score) }}</span>
          </div>
          <div
            v-if="src.url"
            class="detail-row"
          >
            <span class="detail-key">url:</span>
            <a
              :href="src.url"
              target="_blank"
              rel="noopener noreferrer"
              class="detail-url"
              :data-testid="`citation-url-${idx}`"
            >{{ src.url }}</a>
          </div>
          <!-- 兜底：把 source 上没识别的字段也展示出来，便于调试未知字段 -->
          <pre
            v-if="
              !src.id &&
                !src.title &&
                typeof src.score !== 'number' &&
                !src.url
            "
            class="detail-raw"
          >{{ JSON.stringify(src, null, 2) }}</pre>
        </div>
      </li>
    </ul>

    <p
      v-else
      class="citation-empty"
      data-testid="citation-empty"
    >
      (本次 run 未引用任何 RAG 文档)
    </p>
  </section>
</template>

<style scoped>
.citation-widget {
  border: 1px solid var(--citation-color);
  border-radius: var(--border-radius);
  padding: var(--panel-padding);
  background: #ecfeff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.citation-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--citation-color);
  font-weight: 600;
}

.citation-icon {
  font-size: 18px;
}

.citation-title {
  font-size: 15px;
}

.citation-run-id {
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 400;
}

.citation-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.citation-item {
  background: #ffffff;
  border-radius: 4px;
  overflow: hidden;
}

.citation-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: #1f2937;
}

.citation-row:hover {
  background: #f0f9ff;
}

.citation-index {
  color: var(--citation-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  min-width: 32px;
}

.citation-label {
  flex: 1;
  font-size: 14px;
}

.citation-score {
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.citation-toggle {
  color: var(--citation-color);
  font-size: 12px;
  min-width: 16px;
  text-align: center;
}

.citation-detail {
  padding: 8px 12px 10px 50px;
  border-top: 1px solid #e0f2fe;
  background: #f0f9ff;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-row {
  display: flex;
  gap: 6px;
  font-size: 13px;
}

.detail-key {
  color: var(--muted-color);
  min-width: 50px;
  font-weight: 500;
}

.detail-value {
  color: #1f2937;
  word-break: break-all;
}

.detail-url {
  color: #0e7490;
  text-decoration: underline;
  word-break: break-all;
}

.detail-raw {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: #1f2937;
  background: #ffffff;
  padding: 6px;
  border-radius: 4px;
  white-space: pre-wrap;
}

.citation-empty {
  color: var(--muted-color);
  font-style: italic;
  font-size: 13px;
  padding: 4px 0;
}
</style>
