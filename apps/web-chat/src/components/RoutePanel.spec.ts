import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RoutePanel from './RoutePanel.vue'
import type { RouteDecision } from '../composables/useBusinessEvents'

function makeDecision(overrides: Partial<RouteDecision> = {}): RouteDecision {
  return {
    query: '对比网上关于 RAG 的最新文章和我们内部知识库',
    intent: 'rag',
    target_profiles: ['rag'],
    is_multi_intent: false,
    confidence: 0.7,
    matched_keywords: ['RAG', '知识库'],
    ...overrides,
  }
}

describe('RoutePanel', () => {
  it('单意图：显示 intent + confidence + 单个 profile + 不显示多意图标签', () => {
    const wrapper = mount(RoutePanel, {
      props: {
        decision: makeDecision({
          intent: 'rag',
          target_profiles: ['rag'],
          is_multi_intent: false,
          confidence: 0.7,
          matched_keywords: ['RAG', '知识库'],
        }),
      },
    })

    expect(wrapper.find('[data-testid="route-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="route-panel"]').attributes('data-intent')).toBe('rag')
    expect(wrapper.find('[data-testid="route-panel"]').attributes('data-multi-intent')).toBe(
      'false',
    )
    // 单 profile：只渲染 1 个 chip
    expect(wrapper.findAll('[data-testid^="profile-chip-"]')).toHaveLength(1)
    expect(wrapper.find('[data-testid="profile-chip-rag"]').exists()).toBe(true)
    // 多意图标签不应出现
    expect(wrapper.find('[data-testid="route-multi-intent"]').exists()).toBe(false)
    // 置信度格式化为 2 位小数
    expect(wrapper.text()).toContain('confidence=0.70')
  })

  it('多意图：显示 ⚠ 多意图 标签 + profile 链路用 → 串联（保留优先级顺序）', () => {
    const wrapper = mount(RoutePanel, {
      props: {
        decision: makeDecision({
          intent: 'database',
          target_profiles: ['database', 'rag', 'synthesizer'],
          is_multi_intent: true,
          confidence: 0.8,
        }),
      },
    })

    expect(wrapper.find('[data-testid="route-multi-intent"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="route-multi-intent"]').text()).toContain('多意图')

    // 3 个 chip，按给定顺序渲染
    const chips = wrapper.findAll('[data-testid^="profile-chip-"]')
    expect(chips).toHaveLength(3)
    expect(chips[0].text()).toContain('database')
    expect(chips[1].text()).toContain('rag')
    expect(chips[2].text()).toContain('synthesizer')

    // 链路中 → 连接符：2 个 → 出现 2 次（n-1 个）
    expect(wrapper.text().match(/→/g)?.length).toBe(2)

    // data-multi-intent 反映到 attribute
    expect(wrapper.find('[data-testid="route-panel"]').attributes('data-multi-intent')).toBe(
      'true',
    )
  })

  it('无关键词匹配：matched 区显示 "(无关键词匹配)" 占位', () => {
    const wrapper = mount(RoutePanel, {
      props: {
        decision: makeDecision({
          matched_keywords: [],
        }),
      },
    })

    const meta = wrapper.find('[data-testid="route-meta"]')
    expect(meta.exists()).toBe(true)
    expect(meta.text()).toContain('(无关键词匹配)')
  })

  it('关键词列表：按 Router 输出的顺序以逗号分隔展示', () => {
    const wrapper = mount(RoutePanel, {
      props: {
        decision: makeDecision({
          matched_keywords: ['内部', '知识库', 'FAQ'],
        }),
      },
    })

    const meta = wrapper.find('[data-testid="route-meta"]')
    expect(meta.text()).toContain('内部, 知识库, FAQ')
  })

  it('置信度 3 位小数也展示为 2 位（toFixed 行为）', () => {
    // 注：JS toFixed 走 IEEE754；0.825 实际是 0.82499... → "0.82"
    // 用 0.836 明确测试"四舍五入到 0.84"
    const wrapper = mount(RoutePanel, {
      props: {
        decision: makeDecision({
          confidence: 0.836,
        }),
      },
    })
    expect(wrapper.text()).toContain('confidence=0.84')
  })
})
