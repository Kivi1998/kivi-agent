<script setup lang="ts">
// MetricsBar：7 指标条形图（ECharts 真画图）
// 复用 Wave 3 ChartWidget 的 echarts 集成模式：use() 模块化注册 + VChart
import { computed } from 'vue'
import VChart from 'vue-echarts'

import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent
} from 'echarts/components'

import type { MetricsReport } from '@/types/api'

// 模块加载时一次性注册（use() 幂等）
use([CanvasRenderer, BarChart, TitleComponent, TooltipComponent, GridComponent])

const props = defineProps<{
  /** 指标报告；null 时不渲染 */
  metrics: MetricsReport | null
  /** 报告来源标题（展示用，如 "全局汇总" / "run-1"） */
  title?: string
}>()

/** 7 个指标的归一化 bar 配置（用百分比展示 0-1 范围的指标；其它原始值） */
interface BarRow {
  name: string
  value: number
  unit: string
  isPercent: boolean
}

/** 7 指标：1 任务成功率 / 2 路由正确率 / 3 Tool 选择 exact / 4 Tool 选择 contain / 5 RAG 引用 / 6 平均延迟 / 7 总成本 */
const barData = computed<BarRow[]>(() => {
  if (!props.metrics) return []
  const m = props.metrics.metrics
  return [
    { name: '任务成功率', value: m.task_success_rate.rate, unit: '%', isPercent: true },
    { name: '路由正确率', value: m.route_accuracy.rate, unit: '%', isPercent: true },
    { name: 'Tool 精确匹配', value: m.tool_selection_accuracy.exact_match_rate, unit: '%', isPercent: true },
    { name: 'Tool 包含匹配', value: m.tool_selection_accuracy.contain_match_rate, unit: '%', isPercent: true },
    { name: 'RAG 引用', value: m.rag_citation_accuracy.rate, unit: '%', isPercent: true },
    { name: '平均延迟(s)', value: m.avg_latency_seconds.avg_s, unit: 's', isPercent: false },
    { name: '总成本(USD)', value: m.total_cost_usd.total_usd, unit: '$', isPercent: false }
  ]
})

/** ECharts option：横向 bar，百分比类指标用 0-1 范围 / 绝对值指标按各自范围 */
const chartOption = computed<Record<string, unknown>>(() => {
  const rows = barData.value
  const names = rows.map((r) => r.name)
  const values = rows.map((r) => r.value)
  return {
    title: {
      text: props.title ?? '7 指标',
      left: 'left',
      textStyle: { color: '#c9d1d9', fontSize: 14, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown): string => {
        const arr = Array.isArray(params) ? (params as Array<{ dataIndex: number; value: number }>) : []
        if (arr.length === 0) return ''
        const idx = arr[0]?.dataIndex ?? 0
        const row = rows[idx]
        if (!row) return ''
        const display = row.isPercent
          ? (row.value * 100).toFixed(1) + '%'
          : row.value.toFixed(4) + ' ' + row.unit
        return `${row.name}: ${display}`
      }
    },
    grid: { left: 100, right: 30, top: 40, bottom: 20 },
    xAxis: {
      type: 'value',
      axisLine: { lineStyle: { color: '#1e242e' } },
      splitLine: { lineStyle: { color: '#1e242e' } },
      axisLabel: { color: '#6b7280' }
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#1e242e' } },
      axisLabel: { color: '#c9d1d9', fontSize: 12 }
    },
    series: [
      {
        type: 'bar',
        data: values,
        itemStyle: { color: '#06b6d4' },
        label: {
          show: true,
          position: 'right',
          color: '#c9d1d9',
          fontSize: 11,
          formatter: (p: { dataIndex: number; value: number }): string => {
            const row = rows[p.dataIndex]
            if (!row) return ''
            return row.isPercent
              ? (p.value * 100).toFixed(1) + '%'
              : p.value.toFixed(4)
          }
        }
      }
    ]
  }
})
</script>

<template>
  <section
    class="metrics-bar"
    data-testid="metrics-bar"
  >
    <div
      v-if="!metrics"
      class="metrics-empty"
      data-testid="metrics-empty"
    >
      暂无指标
    </div>
    <div
      v-else
      class="metrics-chart"
      data-testid="metrics-chart"
    >
      <VChart
        :option="chartOption"
        class="metrics-canvas"
        autoresize
      />
    </div>
  </section>
</template>

<style scoped>
.metrics-bar {
  padding: var(--panel-padding);
  background: var(--bg-panel, #11151c);
  border-radius: var(--border-radius);
  border: 1px solid var(--bg-border, #1e242e);
}

.metrics-empty {
  text-align: center;
  color: var(--muted-color);
  padding: 30px 0;
  font-size: 13px;
}

.metrics-chart {
  background: #0a0e14;
  border-radius: 4px;
  padding: 4px;
}

.metrics-canvas {
  width: 100%;
  height: 360px;
}
</style>
