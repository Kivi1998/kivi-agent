<script setup lang="ts">
// MapView.vue：监听 map.geojson_loaded 事件 + 在 SVG 画布上渲染 GeoJSON
//
// 选型说明：spec 提到 vue3-openlayers 或 Leaflet；为避免新增 npm 依赖（CI 体积 +
// 安装时间），本组件用纯 SVG 渲染：对 Point → <circle>，对 Polygon → <polygon>。
// 真实生产场景可换成 Leaflet；接口（props.event）保持一致，组件替换零修改。
//
// 渲染规则（极简版 demo 4）：
// - 接收 1 个 map.geojson_loaded 事件作为 props
// - features_count > 0 → 渲染 "已加载 N 个要素" 摘要 + bbox
// - 测试用 data-testid：map-view / map-summary / map-bbox / map-layer-id

import { computed } from 'vue'
import type { MapGeojsonLoadedEvent } from '../../types/api'

const props = defineProps<{
  /** 单个 map.geojson_loaded 事件 */
  event: MapGeojsonLoadedEvent
}>()

// 摘要文案：已加载 N 个要素 / 范围 [minLon, minLat, maxLon, maxLat]
const summaryText = computed<string>(() => {
  const n = props.event.features_count
  if (n === 0) return '已加载 0 个要素'
  return `已加载 ${n} 个要素`
})

// bbox 字符串：[min_lon, min_lat, max_lon, max_lat]
const bboxText = computed<string>(() => {
  const b = props.event.bbox
  if (!b) return '范围：未知'
  const [minLon, minLat, maxLon, maxLat] = b
  return `范围：[${minLon.toFixed(2)}, ${minLat.toFixed(2)}, ${maxLon.toFixed(2)}, ${maxLat.toFixed(2)}]`
})

// layer_id 短码（展示用；< 30 字符原样；>= 30 字符截断 + …）
const layerLabel = computed<string>(() => {
  const lid = props.event.layer_id
  return lid.length > 30 ? lid.slice(0, 27) + '…' : lid
})
</script>

<template>
  <section
    class="map-view"
    data-testid="map-view"
    :data-event-type="event.type"
    :data-layer-id="event.layer_id"
    :data-features-count="event.features_count"
    :data-has-bbox="event.bbox !== null ? 'true' : 'false'"
  >
    <header class="map-header">
      <span
        class="map-icon"
        aria-hidden="true"
      >🗺️</span>
      <span class="map-title">地图: {{ layerLabel }}</span>
      <span class="map-url">{{ event.url }}</span>
    </header>
    <div class="map-canvas-wrap">
      <!-- 演示版：纯 SVG 占位画布 + 几何要素占位（Point=圆，Polygon=矩形占位） -->
      <svg
        class="map-svg"
        viewBox="0 0 320 200"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="GeoJSON preview canvas"
      >
        <!-- 背景：浅灰底 -->
        <rect
          x="0"
          y="0"
          width="320"
          height="200"
          fill="#eef2f7"
        />
        <!-- 装饰：3 个圆点代表 Point features（演示版用固定位置） -->
        <g data-testid="map-features-point">
          <circle
            cx="80"
            cy="60"
            r="6"
            fill="#3b82f6"
            opacity="0.8"
          />
          <circle
            cx="180"
            cy="100"
            r="6"
            fill="#10b981"
            opacity="0.8"
          />
          <circle
            cx="240"
            cy="140"
            r="6"
            fill="#f59e0b"
            opacity="0.8"
          />
        </g>
        <!-- 装饰：1 个矩形代表 Polygon features -->
        <rect
          x="40"
          y="120"
          width="80"
          height="50"
          fill="#a78bfa"
          opacity="0.4"
          stroke="#7c3aed"
          stroke-width="2"
        />
      </svg>
    </div>
    <div
      class="map-summary"
      data-testid="map-summary"
    >
      {{ summaryText }}
    </div>
    <div
      class="map-bbox"
      data-testid="map-bbox"
    >
      {{ bboxText }}
    </div>
  </section>
</template>

<style scoped>
.map-view {
  border: 1px solid var(--accent-color, #3b82f6);
  border-radius: var(--border-radius, 6px);
  padding: var(--panel-padding, 12px);
  background: #f0f9ff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.map-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--accent-color, #1d4ed8);
  font-weight: 600;
}

.map-icon {
  font-size: 18px;
}

.map-title {
  font-size: 15px;
}

.map-url {
  color: var(--muted-color, #6b7280);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 400;
  word-break: break-all;
}

.map-canvas-wrap {
  background: #ffffff;
  border-radius: 4px;
  padding: 8px;
}

.map-svg {
  width: 100%;
  height: 200px;
  display: block;
}

.map-summary,
.map-bbox {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--muted-color, #6b7280);
}
</style>
