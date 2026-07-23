<script setup lang="ts">
// DelegationTree：简易委派树（SVG）展示成员 → 委派 sub-task → 完成状态
// 每个 node 渲染为方块；同 member 出/入箭头连接
import { computed } from 'vue'
import type { DelegationStep, MemberOutcome } from '@/types/api'

const props = defineProps<{
  /** team 成员 outcomes（用于渲染节点卡片） */
  members: MemberOutcome[]
  /** 委派步骤（边） */
  steps: DelegationStep[]
}>()

interface Node {
  id: string
  role: string
  x: number
  y: number
  success: boolean
}

interface Edge {
  from: string
  to: string
  label: string
  success: boolean
}

const NODE_W = 140
const NODE_H = 56
const COL_GAP = 220
const PADDING = 24

/** 节点：从 members 中按 id 渲染，水平排列在 top row */
const nodes = computed<Node[]>(() => {
  return props.members.map((m, i) => ({
    id: m.member_id,
    role: m.role,
    x: PADDING + i * COL_GAP,
    y: PADDING,
    success: m.success
  }))
})

/** 边：steps 中同一 from→to 出现多次则垂直堆叠 */
const edges = computed<Edge[]>(() => {
  // 统计每个 from→to 对出现的次数，决定 y 偏移
  const laneCount: Record<string, number> = {}
  return props.steps.map((s) => {
    const key = `${s.from_member}->${s.to_member}`
    const lane = laneCount[key] ?? 0
    laneCount[key] = lane + 1
    return {
      from: s.from_member,
      to: s.to_member,
      label: s.sub_task,
      success: s.success
    }
  })
})

/** SVG 视图框尺寸 */
const viewBox = computed<string>(() => {
  const w = Math.max(NODE_W + PADDING * 2, props.members.length * COL_GAP + PADDING)
  const h = NODE_H * 2 + PADDING * 3
  return `0 0 ${w} ${h}`
})

/** 找节点 x/y */
function nodeById(id: string): Node | undefined {
  return nodes.value.find((n) => n.id === id)
}

/** 边 path（贝塞尔曲线 from 右 → to 左） */
function edgePath(e: Edge): string {
  const a = nodeById(e.from)
  const b = nodeById(e.to)
  if (!a || !b) return ''
  const x1 = a.x + NODE_W
  const y1 = a.y + NODE_H / 2
  const x2 = b.x
  const y2 = b.y + NODE_H / 2
  const cx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
}

/** 边中点（用于渲染 label） */
function edgeMid(e: Edge): { x: number; y: number } {
  const a = nodeById(e.from)
  const b = nodeById(e.to)
  if (!a || !b) return { x: 0, y: 0 }
  return { x: (a.x + NODE_W + b.x) / 2, y: (a.y + b.y + NODE_H) / 2 }
}
</script>

<template>
  <section
    class="delegation-tree"
    data-testid="delegation-tree"
  >
    <header class="dt-header">
      <h3 class="dt-title">
        委派树
      </h3>
      <span
        v-if="edges.length > 0"
        class="dt-count"
        data-testid="delegation-edge-count"
      >{{ edges.length }} 条边</span>
    </header>

    <div
      v-if="members.length === 0"
      class="dt-empty"
      data-testid="delegation-empty"
    >
      暂无委派关系
    </div>

    <div
      v-else
      class="dt-svg-wrap"
    >
      <svg
        :viewBox="viewBox"
        class="dt-svg"
        data-testid="delegation-svg"
        role="img"
        :aria-label="`委派树: ${members.length} 节点, ${edges.length} 边`"
      >
        <!-- edges -->
        <g class="dt-edges">
          <g
            v-for="(e, i) in edges"
            :key="`edge-${i}-${e.from}-${e.to}`"
            class="dt-edge"
            :data-testid="`delegation-edge-${i}`"
            :data-success="e.success ? 'true' : 'false'"
          >
            <path
              :d="edgePath(e)"
              :stroke="e.success ? '#10b981' : '#ef4444'"
              stroke-width="2"
              fill="none"
              stroke-dasharray="4 3"
            />
            <text
              :x="edgeMid(e).x"
              :y="edgeMid(e).y"
              class="dt-edge-label"
              text-anchor="middle"
            >{{ e.label }}</text>
          </g>
        </g>

        <!-- nodes -->
        <g class="dt-nodes">
          <g
            v-for="(n, i) in nodes"
            :key="`node-${n.id}`"
            class="dt-node"
            :data-testid="`delegation-node-${i}`"
            :data-success="n.success ? 'true' : 'false'"
            :transform="`translate(${n.x}, ${n.y})`"
          >
            <rect
              :width="NODE_W"
              :height="NODE_H"
              rx="6"
              :fill="n.success ? '#064e3b' : '#7f1d1d'"
              :stroke="n.success ? '#10b981' : '#ef4444'"
              stroke-width="1.5"
            />
            <text
              :x="NODE_W / 2"
              :y="22"
              class="dt-node-name"
              text-anchor="middle"
            >{{ n.id }}</text>
            <text
              :x="NODE_W / 2"
              :y="42"
              class="dt-node-role"
              text-anchor="middle"
            >{{ n.role }}</text>
          </g>
        </g>
      </svg>
    </div>
  </section>
</template>

<style scoped>
.delegation-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.dt-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--muted-color);
}

.dt-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9d1d9;
  margin: 0;
}

.dt-count {
  font-size: 12px;
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.dt-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 24px 0;
  font-size: 13px;
}

.dt-svg-wrap {
  background: #0a0e14;
  border: 1px solid #1e242e;
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
}

.dt-svg {
  width: 100%;
  min-height: 160px;
  height: auto;
}

.dt-edge-label {
  fill: #c9d1d9;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.dt-node-name {
  fill: #c9d1d9;
  font-size: 13px;
  font-weight: 600;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.dt-node-role {
  fill: #6b7280;
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
