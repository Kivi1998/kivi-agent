// DelegationTree 组件测试（2 场景：空 / 2 节点 + 1 边）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DelegationTree from './DelegationTree.vue'
import type { DelegationStep, MemberOutcome } from '@/types/api'

const members: MemberOutcome[] = [
  {
    member_id: 'researcher',
    role: 'research',
    success: true,
    steps: 5,
    tool_calls: 3,
    finished_at: '2026-07-23T00:00:30Z',
    final_answer: '找到 3 篇资料'
  },
  {
    member_id: 'writer',
    role: 'writer',
    success: true,
    steps: 4,
    tool_calls: 1,
    finished_at: '2026-07-23T00:01:00Z',
    final_answer: '已生成报告'
  }
]

describe('DelegationTree', () => {
  it('空：显示 "暂无委派关系" empty state + 不渲染 svg', () => {
    const wrapper = mount(DelegationTree, {
      props: { members: [], steps: [] }
    })
    expect(wrapper.find('[data-testid="delegation-tree"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="delegation-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="delegation-svg"]').exists()).toBe(false)
  })

  it('2 节点 + 1 边：渲染 svg + 节点 + 边', () => {
    const steps: DelegationStep[] = [
      {
        step_id: 'd-1',
        from_member: 'researcher',
        to_member: 'writer',
        sub_task: '汇总报告',
        message: '资料已收集',
        success: true,
        ts: '2026-07-23T00:00:30Z'
      }
    ]
    const wrapper = mount(DelegationTree, {
      props: { members, steps }
    })
    expect(wrapper.find('[data-testid="delegation-svg"]').exists()).toBe(true)
    // 2 个节点
    expect(wrapper.findAll('[data-testid^="delegation-node-"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="delegation-node-0"]').text()).toContain(
      'researcher'
    )
    expect(wrapper.find('[data-testid="delegation-node-0"]').text()).toContain(
      'research'
    )
    // 1 条边
    expect(wrapper.findAll('[data-testid^="delegation-edge-"]')).toHaveLength(2)
    // 边 group 节点（带 -0/-1 后缀，不带 -count 文本节点）
    const edges = wrapper.findAll('.dt-edge')
    expect(edges).toHaveLength(1)
    expect(edges[0]?.text()).toContain('汇总报告')
    // 边计数
    expect(wrapper.find('[data-testid="delegation-edge-count"]').text()).toContain(
      '1'
    )
  })
})
