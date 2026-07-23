// IterationCountBadge 组件测试（3 场景：0 灰 / 1 绿 / 2 黄 / 3 红 + 文本）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import IterationCountBadge from './IterationCountBadge.vue'

describe('IterationCountBadge', () => {
  it('0 轮：data-level=gray + "未运行"', () => {
    const wrapper = mount(IterationCountBadge, { props: { iterations: 0 } })
    expect(wrapper.find('[data-testid="iter-badge-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="iter-badge-0"]').attributes('data-level')).toBe(
      'gray'
    )
    expect(wrapper.text()).toContain('未运行')
  })

  it('1 轮：data-level=green + "1 轮（一次过）"', () => {
    const wrapper = mount(IterationCountBadge, { props: { iterations: 1 } })
    expect(wrapper.find('[data-testid="iter-badge-1"]').attributes('data-level')).toBe(
      'green'
    )
    expect(wrapper.text()).toContain('1 轮')
    expect(wrapper.text()).toContain('一次过')
  })

  it('2 轮：data-level=yellow + "2 轮" / 3 轮：data-level=red + "3 轮"', () => {
    const w2 = mount(IterationCountBadge, { props: { iterations: 2 } })
    expect(w2.find('[data-testid="iter-badge-2"]').attributes('data-level')).toBe(
      'yellow'
    )
    expect(w2.text()).toContain('2 轮')

    const w3 = mount(IterationCountBadge, { props: { iterations: 3 } })
    expect(w3.find('[data-testid="iter-badge-3"]').attributes('data-level')).toBe(
      'red'
    )
    expect(w3.text()).toContain('3 轮')
  })
})
