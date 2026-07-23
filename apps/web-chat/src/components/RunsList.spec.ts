// RunsList 组件测试（3 场景：空 / 1 run / 多 run + 点击事件）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RunsList from './RunsList.vue'
import type { RunSummary } from '@/types/api'

const baseRun: RunSummary = {
  run_id: 'run-1',
  started_at: '2026-07-23T00:00:00Z',
  case_count: 5,
  success_count: 4
}

describe('RunsList', () => {
  it('空：显示 "暂无评测运行" empty state + 不显示 table', () => {
    const wrapper = mount(RunsList, { props: { runs: [] } })
    expect(wrapper.find('[data-testid="runs-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="runs-table"]').exists()).toBe(false)
  })

  it('1 run：渲染 1 行 + 表格列 + 成功率', () => {
    const wrapper = mount(RunsList, { props: { runs: [baseRun] } })
    expect(wrapper.findAll('[data-testid^="runs-row-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="runs-row-run-1"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('run-1')
    // 4/5 = 80.0%
    expect(wrapper.text()).toContain('80.0%')
    expect(wrapper.find('[data-testid="runs-count"]').text()).toContain('1')
  })

  it('多 run：渲染多行 + 点击行触发 select 事件 + started_at=null 显示占位', async () => {
    const runs: RunSummary[] = [
      baseRun,
      { ...baseRun, run_id: 'run-2', started_at: null, case_count: 3, success_count: 3 }
    ]
    const wrapper = mount(RunsList, { props: { runs } })
    expect(wrapper.findAll('[data-testid^="runs-row-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="runs-row-run-2"]').text()).toContain('(未开始)')

    // 点击 run-1 触发 select
    await wrapper.find('[data-testid="runs-row-run-1"]').trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['run-1'])

    // 点击 run-2 也触发
    await wrapper.find('[data-testid="runs-row-run-2"]').trigger('click')
    const emitted2 = wrapper.emitted('select')
    expect(emitted2?.[1]).toEqual(['run-2'])
  })
})
