// RunsList (coding) 组件测试（3 场景：空 / 1 run / 多 run + 点击事件）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RunsList from './RunsList.vue'
import type { CodingRunItem } from '@/types/api'

const baseRun: CodingRunItem = {
  run_id: 'crun-1',
  task: 'Write a function add(a, b) that returns a + b',
  test_file: 'tests/test_add.py',
  iteration_count: 2,
  success: true,
  started_at: '2026-07-23T00:00:00Z',
  finished_at: '2026-07-23T00:00:08Z'
}

describe('Coding RunsList', () => {
  it('空：显示 "暂无 coding run" empty state + 不显示 table', () => {
    const wrapper = mount(RunsList, { props: { runs: [] } })
    expect(wrapper.find('[data-testid="cruns-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cruns-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="cruns-table"]').exists()).toBe(false)
  })

  it('1 run：渲染 1 行 + 显示 task 摘要 + test_file + iteration + success', () => {
    const wrapper = mount(RunsList, { props: { runs: [baseRun] } })
    expect(wrapper.findAll('[data-testid^="cruns-row-"]')).toHaveLength(1)
    const row = wrapper.find('[data-testid="cruns-row-crun-1"]')
    expect(row.text()).toContain('crun-1')
    expect(row.text()).toContain('Write a function')
    expect(row.text()).toContain('tests/test_add.py')
    expect(row.text()).toContain('2')
    expect(row.text()).toContain('✓')
    expect(row.attributes('data-success')).toBe('true')
    expect(wrapper.find('[data-testid="cruns-count"]').text()).toContain('1')
  })

  it('多 run：渲染多行 + 点击触发 select + null started_at 显示占位 + 失败显示 ✗', async () => {
    const runs: CodingRunItem[] = [
      baseRun,
      {
        ...baseRun,
        run_id: 'crun-2',
        success: false,
        started_at: null,
        iteration_count: 3
      }
    ]
    const wrapper = mount(RunsList, { props: { runs } })
    expect(wrapper.findAll('[data-testid^="cruns-row-"]')).toHaveLength(2)
    const row2 = wrapper.find('[data-testid="cruns-row-crun-2"]')
    expect(row2.text()).toContain('(未开始)')
    expect(row2.text()).toContain('✗')
    expect(row2.text()).toContain('3')

    // 点击 crun-1
    await wrapper.find('[data-testid="cruns-row-crun-1"]').trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeTruthy()
    expect(emitted?.[0]).toEqual(['crun-1'])

    // 点击 crun-2
    await wrapper.find('[data-testid="cruns-row-crun-2"]').trigger('click')
    expect(wrapper.emitted('select')?.[1]).toEqual(['crun-2'])
  })
})
