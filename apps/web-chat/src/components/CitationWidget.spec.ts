import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CitationWidget from './CitationWidget.vue'
import type { RagSourcesCitedEvent } from '../types/api'

function makeEvent(sources: RagSourcesCitedEvent['sources']): RagSourcesCitedEvent {
  return {
    type: 'rag.sources_cited',
    run_id: 'run-cite-1',
    sources,
    ts: '2026-07-23T12:00:00Z',
  }
}

describe('CitationWidget', () => {
  it('3 条 sources：列表展示 id / title / score，点击可展开', async () => {
    const sources = [
      { id: 'kb-001', title: 'RAG 系统架构综述', score: 0.95 },
      { id: 'kb-002', title: '企业内部知识库最佳实践', score: 0.92 },
      { id: 'kb-003', title: '向量检索实战', score: 0.88 },
    ]
    const wrapper = mount(CitationWidget, {
      props: { event: makeEvent(sources) },
    })

    expect(wrapper.find('[data-testid="citation-widget"]').exists()).toBe(true)
    expect(
      wrapper.find('[data-testid="citation-widget"]').attributes('data-source-count'),
    ).toBe('3')

    const items = wrapper.findAll('[data-testid^="citation-source-"]')
    expect(items).toHaveLength(3)

    // 折叠态：每行展示 [idx] + title + score
    expect(wrapper.find('[data-testid="citation-source-0"]').text()).toContain('[1]')
    expect(wrapper.find('[data-testid="citation-source-0"]').text()).toContain(
      'RAG 系统架构综述',
    )
    expect(wrapper.find('[data-testid="citation-source-0"]').text()).toContain('score=0.95')

    // 默认折叠：detail 节点不应存在
    expect(wrapper.find('[data-testid="citation-detail-0"]').exists()).toBe(false)

    // 点击第 1 条 → 展开 detail
    await wrapper.find('[data-testid="citation-source-0"] button').trigger('click')
    expect(wrapper.find('[data-testid="citation-detail-0"]').exists()).toBe(true)
    // 再次点击 → 收起
    await wrapper.find('[data-testid="citation-source-0"] button').trigger('click')
    expect(wrapper.find('[data-testid="citation-detail-0"]').exists()).toBe(false)
  })

  it('0 条 sources：显示空态 "(本次 run 未引用任何 RAG 文档)"，不渲染列表', () => {
    const wrapper = mount(CitationWidget, {
      props: { event: makeEvent([]) },
    })

    expect(
      wrapper.find('[data-testid="citation-widget"]').attributes('data-source-count'),
    ).toBe('0')
    expect(wrapper.find('[data-testid="citation-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="citation-empty"]').text()).toContain('未引用')
    expect(wrapper.findAll('[data-testid^="citation-source-"]')).toHaveLength(0)
  })

  it('source 含 url 时，detail 渲染为 <a> 链接（target=_blank）', async () => {
    const wrapper = mount(CitationWidget, {
      props: {
        event: makeEvent([
          {
            id: 'kb-100',
            title: 'RAG 综述',
            score: 0.91,
            url: 'https://example.com/rag-survey',
          },
        ]),
      },
    })

    // 先展开
    await wrapper.find('[data-testid="citation-source-0"] button').trigger('click')

    const link = wrapper.find('[data-testid="citation-url-0"]')
    expect(link.exists()).toBe(true)
    expect(link.element.tagName).toBe('A')
    expect(link.attributes('href')).toBe('https://example.com/rag-survey')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
  })

  it('source 缺 score 时显示 —（em dash）', () => {
    const wrapper = mount(CitationWidget, {
      props: {
        event: makeEvent([{ id: 'kb-200', title: '无 score 的引用' }]),
      },
    })
    expect(wrapper.find('[data-testid="citation-source-0"]').text()).toContain('score=—')
  })
})
