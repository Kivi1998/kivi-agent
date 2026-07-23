<script setup lang="ts">
// MemorySearchBar：向量检索（q + top_k 滑块）+ 命中结果列表
// 提交 → emit('search', { q, topK })；点击结果行 → emit('select', id)
import { computed, ref, watch } from 'vue'
import type { MemorySearchResult } from '@/types/api'
import { MEMORY_STATUS_LABELS, MEMORY_TYPE_LABELS } from '@/api/memory'

const props = defineProps<{
  results: MemorySearchResult[]
  loading?: boolean
  lastQuery?: string
  lastTopK?: number
}>()

const emit = defineEmits<{
  (e: 'search', payload: { q: string; topK: number }): void
  (e: 'select', id: string): void
}>()

const q = ref<string>('')
const topK = ref<number>(5)

const isEmpty = computed<boolean>(
  () => !props.loading && props.results.length === 0
)

watch(
  () => [props.lastQuery, props.lastTopK],
  ([nextQ, nextK]) => {
    if (typeof nextQ === 'string') q.value = nextQ
    if (typeof nextK === 'number') topK.value = nextK
  }
)

function onSubmit(): void {
  if (q.value.trim().length === 0) return
  emit('search', { q: q.value.trim(), topK: topK.value })
}

function onResultClick(id: string): void {
  emit('select', id)
}

function scorePct(s: number): string {
  return (s * 100).toFixed(1) + '%'
}
</script>

<template>
  <section
    class="memory-search"
    data-testid="memory-search-bar"
  >
    <header class="ms-header">
      <h3 class="ms-title">
        向量检索
      </h3>
    </header>

    <form
      class="ms-form"
      data-testid="memory-search-form"
      @submit.prevent="onSubmit"
    >
      <input
        v-model="q"
        type="text"
        placeholder="输入检索问题（向量检索）..."
        class="ms-input"
        data-testid="memory-search-input"
      >
      <label class="ms-topk">
        <span class="ms-topk-label">top_k</span>
        <input
          v-model.number="topK"
          type="range"
          min="1"
          max="20"
          step="1"
          data-testid="memory-search-topk"
        >
        <span
          class="ms-topk-value"
          data-testid="memory-search-topk-value"
        >{{ topK }}</span>
      </label>
      <button
        type="submit"
        class="ms-btn"
        :disabled="q.trim().length === 0"
        data-testid="memory-search-submit"
      >
        搜索
      </button>
    </form>

    <div
      v-if="loading"
      class="ms-loading"
      data-testid="memory-search-loading"
    >
      检索中...
    </div>

    <div
      v-else-if="isEmpty"
      class="ms-empty"
      data-testid="memory-search-empty"
    >
      暂无检索结果
    </div>

    <ul
      v-else
      class="ms-results"
      data-testid="memory-search-results"
    >
      <li
        v-for="r in results"
        :key="r.id"
        :data-testid="`memory-search-hit-${r.id}`"
        class="ms-result"
        :data-score="r.score"
        @click="onResultClick(r.id)"
      >
        <div class="ms-result-head">
          <span class="ms-result-id">{{ r.id }}</span>
          <span
            class="ms-result-score"
            data-testid="memory-search-hit-score"
          >{{ scorePct(r.score) }}</span>
        </div>
        <div class="ms-result-content">
          {{ r.content }}
        </div>
        <div class="ms-result-meta">
          <span class="badge">{{ MEMORY_TYPE_LABELS[r.memory_type] }}</span>
          <span class="badge badge-status">{{ MEMORY_STATUS_LABELS[r.status] }}</span>
          <span class="ms-result-source">来源: {{ r.source || '(无)' }}</span>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.memory-search {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.ms-header {
  border-bottom: 1px solid #1e242e;
  padding-bottom: 6px;
}

.ms-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.ms-form {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.ms-input {
  flex: 1;
  min-width: 220px;
  background: #0a0e14;
  color: #c9d1d9;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 13px;
  font-family: inherit;
}

.ms-input:focus {
  outline: 1px solid #6366f1;
  border-color: #6366f1;
}

.ms-topk {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted-color);
  font-size: 12px;
}

.ms-topk-label {
  font-weight: 500;
}

.ms-topk input[type='range'] {
  width: 100px;
  accent-color: #6366f1;
}

.ms-topk-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #c9d1d9;
  min-width: 24px;
  text-align: right;
}

.ms-btn {
  background: #4338ca;
  color: #fff;
  border: 1px solid #6366f1;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}

.ms-btn:hover:not(:disabled) {
  background: #6366f1;
}

.ms-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ms-loading,
.ms-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 14px 0;
  font-size: 13px;
}

.ms-results {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 420px;
  overflow-y: auto;
}

.ms-result {
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.ms-result:hover {
  background: #1e242e;
}

.ms-result-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.ms-result-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #6366f1;
  font-size: 11px;
}

.ms-result-score {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: #10b981;
  font-size: 12px;
  font-weight: 600;
}

.ms-result-content {
  color: #c9d1d9;
  font-size: 12px;
  line-height: 1.4;
  margin-bottom: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ms-result-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--muted-color);
}

.ms-result-source {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #1e293b;
  color: #c9d1d9;
}

.badge-status {
  background: #064e3b;
  color: #10b981;
}
</style>
