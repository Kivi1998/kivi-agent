<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'

// ECharts 模块化注册：仅引入本组件会用到的图表类型 + 通用 component
// 完整 ECharts 体积 1MB+，按需引入可降到 ~200KB（gzip 后 ~70KB）
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
} from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent,
  ToolboxComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomComponent,
} from 'echarts/components'

import type { ChartRenderedEvent } from '../types/api'

// 在模块加载时一次性注册（use() 内部幂等）
use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent,
  ToolboxComponent,
  MarkLineComponent,
  MarkAreaComponent,
  DataZoomComponent,
])

/**
 * ChartWidget — ECharts 真实画图组件。
 *
 * 对应 TUI `src/kivi_agent/tui/chart_metadata_widget.py`：magenta 卡片 + 标题 +
 * option dict 渲染区。Web 版关键差异：option_dict 透传给 vue-echarts 真实画图，
 * 不只 mock 展示 metadata。
 *
 * Props:
 *   event - ChartRenderedEvent（来自 chart.rendered 事件）
 */
const props = defineProps<{
  event: ChartRenderedEvent
}>()

// 透传 option：vue-echarts 会在 option 引用变化时自动 setOption
const chartOption = computed<Record<string, unknown>>(() => {
  const opt = props.event.option_dict
  // 防御：option_dict 缺失或非对象时降级为占位 option
  if (opt && typeof opt === 'object' && !Array.isArray(opt)) {
    return opt
  }
  return {
    title: { text: '(invalid option_dict)', left: 'center' },
    xAxis: { type: 'category', data: [] },
    yAxis: { type: 'value' },
    series: [],
  }
})

// 从 option_dict 提取 type 字段（标题栏展示用）
const chartType = computed<string>(() => {
  const opt = props.event.option_dict
  if (opt && typeof opt === 'object' && !Array.isArray(opt) && 'type' in opt) {
    return String((opt as Record<string, unknown>).type)
  }
  return 'unknown'
})
</script>

<template>
  <section
    class="chart-widget"
    data-testid="chart-widget"
    :data-chart-id="event.chart_id"
    :data-chart-type="chartType"
  >
    <header class="chart-header">
      <span
        class="chart-icon"
        aria-hidden="true"
      >📊</span>
      <span class="chart-title">图表: {{ event.chart_id }}</span>
      <span class="chart-type">type={{ chartType }}</span>
      <span class="chart-run-id">run_id={{ event.run_id }}</span>
    </header>
    <div
      class="chart-render"
      :data-testid="`chart-render-${event.chart_id}`"
      :data-option-keys="Object.keys(chartOption).join(',')"
    >
      <VChart
        :option="chartOption"
        class="chart-canvas"
        autoresize
      />
    </div>
  </section>
</template>

<style scoped>
.chart-widget {
  border: 1px solid var(--chart-color);
  border-radius: var(--border-radius);
  padding: var(--panel-padding);
  background: #fdf4ff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chart-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--chart-color);
  font-weight: 600;
}

.chart-icon {
  font-size: 18px;
}

.chart-title {
  font-size: 15px;
}

.chart-type,
.chart-run-id {
  color: var(--muted-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 400;
}

.chart-render {
  background: #ffffff;
  border-radius: 4px;
  padding: 8px;
  min-height: 240px;
}

.chart-canvas {
  width: 100%;
  height: 320px;
}
</style>
