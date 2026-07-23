<script setup lang="ts">
// PatchDiffViewer：轻量级 unified diff viewer（不上 monaco）
// 把 unified diff 文本按行解析，+ 行绿、- 行红、@@ 行黄、其它行原色
// 提供 patch 选择器（按 patch_id）
import { computed, ref, watch } from 'vue'
import type { PatchRecord } from '@/types/api'

const props = defineProps<{
  patches: PatchRecord[]
}>()

/** 当前选中的 patch index */
const selectedIdx = ref<number>(0)

/** patches 为空时重置到 0 */
watch(
  () => props.patches.length,
  () => {
    if (selectedIdx.value >= props.patches.length) {
      selectedIdx.value = 0
    }
  }
)

interface DiffLine {
  kind: 'add' | 'remove' | 'context' | 'meta'
  text: string
}

/** 解析 unified diff → DiffLine 列表 */
function parseDiff(diff: string): DiffLine[] {
  if (!diff) return []
  const lines = diff.split('\n')
  return lines.map((line) => {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      return { kind: 'add', text: line }
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      return { kind: 'remove', text: line }
    }
    if (line.startsWith('@@')) {
      return { kind: 'meta', text: line }
    }
    return { kind: 'context', text: line }
  })
}

const currentPatch = computed<PatchRecord | null>(() => {
  return props.patches[selectedIdx.value] ?? null
})

const diffLines = computed<DiffLine[]>(() => {
  const p = currentPatch.value
  if (!p) return []
  return parseDiff(p.diff)
})

/** hunks 命中率字符串（"1/1"） */
function hunkRate(p: PatchRecord): string {
  return `${p.hunks_applied}/${p.hunks_proposed}`
}

/** 切换 patch */
function onSelectPatch(idx: number): void {
  selectedIdx.value = idx
}
</script>

<template>
  <section
    class="patch-diff"
    data-testid="patch-diff-viewer"
  >
    <header class="pd-header">
      <h3 class="pd-title">
        Patch Diff
      </h3>
      <span
        v-if="patches.length > 0"
        class="pd-count"
        data-testid="patch-diff-count"
      >{{ patches.length }} 个 patch</span>
    </header>

    <div
      v-if="patches.length === 0"
      class="pd-empty"
      data-testid="patch-diff-empty"
    >
      暂无 patch
    </div>

    <div
      v-else
      class="pd-body"
    >
      <div
        class="pd-tabs"
        data-testid="patch-diff-tabs"
      >
        <button
          v-for="(p, i) in patches"
          :key="p.patch_id"
          type="button"
          :class="['pd-tab', { active: i === selectedIdx }]"
          :data-testid="`patch-tab-${i}`"
          @click="onSelectPatch(i)"
        >
          #{{ i + 1 }} {{ p.file_path }} (iter {{ p.iteration }}, {{ hunkRate(p) }})
        </button>
      </div>

      <div
        v-if="currentPatch"
        class="pd-meta"
        data-testid="patch-diff-meta"
      >
        <span class="meta-item">file: <code>{{ currentPatch.file_path }}</code></span>
        <span class="meta-item">iter: {{ currentPatch.iteration }}</span>
        <span class="meta-item">ts: {{ currentPatch.ts }}</span>
      </div>

      <pre
        v-if="diffLines.length > 0"
        class="pd-pre"
        data-testid="patch-diff-pre"
      ><span
        v-for="(line, i) in diffLines"
        :key="i"
        :class="['pd-line', `pd-line-${line.kind}`]"
      >{{ line.text }}
</span></pre>

      <div
        v-else
        class="pd-no-diff"
        data-testid="patch-diff-no-diff"
      >
        patch 内容为空
      </div>
    </div>
  </section>
</template>

<style scoped>
.patch-diff {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.pd-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.pd-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.pd-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.pd-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 20px 0;
  font-size: 13px;
}

.pd-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pd-tab {
  background: #0a0e14;
  border: 1px solid #1e242e;
  color: var(--muted-color);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.pd-tab:hover {
  background: #1e242e;
  color: #c9d1d9;
}

.pd-tab.active {
  background: #1e242e;
  border-color: #d946ef;
  color: #d946ef;
}

.pd-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.pd-meta code {
  color: var(--route-panel-color, #06b6d4);
}

.pd-pre {
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 10px 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
}

.pd-line {
  display: block;
  white-space: pre;
}

.pd-line-add {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

.pd-line-remove {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.pd-line-meta {
  color: #eab308;
}

.pd-line-context {
  color: #c9d1d9;
}

.pd-no-diff {
  color: var(--muted-color);
  font-size: 12px;
  padding: 12px;
  text-align: center;
}
</style>
