// TestHistoryTimeline 组件测试（2 场景：空 / 2 轮 + 失败/通过标记 + 编译状态）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TestHistoryTimeline from './TestHistoryTimeline.vue'
import type { TestRunRecord } from '@/types/api'

const passingRecord: TestRunRecord = {
  iteration: 1,
  tests_total: 1,
  tests_passed: 1,
  tests_failed: 0,
  compile_passed: true,
  raw_output: '1 passed in 0.1s',
  ts: '2026-07-23T00:00:04Z'
}

const failingRecord: TestRunRecord = {
  iteration: 2,
  tests_total: 2,
  tests_passed: 1,
  tests_failed: 1,
  compile_passed: true,
  raw_output: '1 failed, 1 passed',
  ts: '2026-07-23T00:00:08Z'
}

describe('TestHistoryTimeline', () => {
  it('空：显示 "暂无测试记录" empty state + 不渲染 list', () => {
    const wrapper = mount(TestHistoryTimeline, { props: { records: [] } })
    expect(wrapper.find('[data-testid="test-history-timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="test-history-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="test-history-list"]').exists()).toBe(false)
  })

  it('多轮：渲染 2 行 + 全通过显示 ✓ 编译 + 失败显示 failed N', () => {
    const wrapper = mount(TestHistoryTimeline, {
      props: { records: [passingRecord, failingRecord] }
    })
    const items = wrapper.findAll('[data-testid^="test-history-iter-"]')
    expect(items).toHaveLength(2)
    // iter 1: passed
    const iter1 = wrapper.find('[data-testid="test-history-iter-1"]')
    expect(iter1.text()).toContain('iter 1')
    expect(iter1.text()).toContain('1/1')
    expect(iter1.text()).toContain('✓ 编译')
    expect(iter1.attributes('data-passed')).toBe('true')

    // iter 2: failed
    const iter2 = wrapper.find('[data-testid="test-history-iter-2"]')
    expect(iter2.text()).toContain('iter 2')
    expect(iter2.text()).toContain('1/2')
    expect(iter2.text()).toContain('failed 1')
    expect(iter2.text()).toContain('✓ 编译')
    expect(iter2.attributes('data-passed')).toBe('false')

    // 计数
    expect(wrapper.find('[data-testid="test-history-count"]').text()).toContain('2')
  })
})
