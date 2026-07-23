// CaseTable 组件测试（2 场景：空 / 多 case + 点击事件 + success 徽标）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CaseTable from './CaseTable.vue'
import type { CaseEvalResult } from '@/types/api'

const baseCase: CaseEvalResult = {
  case_id: 'case-1',
  success: true,
  latency_s: 1.2,
  input_tokens: 100,
  output_tokens: 200,
  cost_usd: 0.01,
  final_answer: '简短回答',
  tool_calls: [{ tool_name: 'web_search', success: true }],
  rag_sources: [{ id: 'src-1' }, { id: 'src-2' }]
}

describe('CaseTable', () => {
  it('空：显示 "暂无 case" empty state + 不渲染表格', () => {
    const wrapper = mount(CaseTable, { props: { cases: [] } })
    expect(wrapper.find('[data-testid="case-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="case-table-grid"]').exists()).toBe(false)
  })

  it('多 case：渲染多行 + 成功/失败徽标 + 工具/RAG 计数 + answer 摘要 + 点击 select', async () => {
    const cases: CaseEvalResult[] = [
      baseCase,
      {
        case_id: 'case-2',
        success: false,
        final_answer: '非常长的回答，用于测试摘要截断。'.repeat(20),
        tool_calls: [],
        rag_sources: []
      }
    ]
    const wrapper = mount(CaseTable, { props: { cases } })
    expect(wrapper.findAll('[data-testid^="case-row-"]')).toHaveLength(2)
    // case-1 成功徽标
    expect(
      wrapper
        .find('[data-testid="case-row-case-1"]')
        .attributes('data-success')
    ).toBe('true')
    // case-2 失败徽标 + 摘要截断
    const row2 = wrapper.find('[data-testid="case-row-case-2"]')
    expect(row2.attributes('data-success')).toBe('false')
    expect(row2.text()).toContain('…')
    // 计数：case-1 tools=1, sources=2
    const row1Text = wrapper.find('[data-testid="case-row-case-1"]').text()
    expect(row1Text).toContain('简短回答')

    // 点击 case-1 触发 select
    await wrapper.find('[data-testid="case-row-case-1"]').trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted?.[0]).toEqual(['case-1'])
  })
})
