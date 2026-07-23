// MapView 组件测试
// 3 个场景：基本渲染 / features_count=0 / bbox=null

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MapView from './MapView.vue'
import type { MapGeojsonLoadedEvent } from '../../types/api'

/** 构造一个标准 map.geojson_loaded 事件 */
function makeEvent(overrides: Partial<MapGeojsonLoadedEvent> = {}): MapGeojsonLoadedEvent {
  return {
    type: 'map.geojson_loaded',
    url: 'https://example.com/parks-1.geojson',
    layer_id: 'parks-1',
    features_count: 3,
    bbox: [116.38, 39.88, 116.42, 39.92],
    ts: '2026-07-23T12:00:00Z',
    ...overrides,
  }
}

describe('MapView', () => {
  it('基本渲染：data-testid=map-view / summary / bbox / layer_id', () => {
    const w = mount(MapView, { props: { event: makeEvent() } })
    const root = w.find('[data-testid="map-view"]')
    expect(root.exists()).toBe(true)
    expect(root.attributes('data-event-type')).toBe('map.geojson_loaded')
    expect(root.attributes('data-layer-id')).toBe('parks-1')
    expect(root.attributes('data-features-count')).toBe('3')
    expect(root.attributes('data-has-bbox')).toBe('true')

    expect(w.find('[data-testid="map-summary"]').text()).toBe('已加载 3 个要素')
    expect(w.find('[data-testid="map-bbox"]').text()).toContain('116.38')
    expect(w.find('[data-testid="map-bbox"]').text()).toContain('39.92')
  })

  it('features_count=0：data-has-bbox 仍为 true + summary 显示 0 个要素', () => {
    const w = mount(MapView, {
      props: { event: makeEvent({ features_count: 0 }) },
    })
    expect(w.find('[data-testid="map-summary"]').text()).toBe('已加载 0 个要素')
    expect(w.attributes('data-features-count')).toBe('0')
    expect(w.attributes('data-has-bbox')).toBe('true')
  })

  it('bbox=null：data-has-bbox=false + bbox 文本显示"未知"', () => {
    const w = mount(MapView, {
      props: { event: makeEvent({ bbox: null }) },
    })
    expect(w.attributes('data-has-bbox')).toBe('false')
    expect(w.find('[data-testid="map-bbox"]').text()).toBe('范围：未知')
  })
})
