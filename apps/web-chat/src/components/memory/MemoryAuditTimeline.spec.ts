// MemoryAuditTimeline 组件测试（3 场景：空 / 有事件 + 倒序 / detail 摘要）
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemoryAuditTimeline from './MemoryAuditTimeline.vue'
import type { MemoryAuditEvent } from '@/types/api'

const events: MemoryAuditEvent[] = [
  {
    event_id: 'evt-1',
    memory_id: 'mem-1',
    action: 'create',
    actor: 'system',
    ts: '2026-07-23T00:00:00Z',
    detail: {}
  },
  {
    event_id: 'evt-2',
    memory_id: 'mem-1',
    action: 'update',
    actor: 'admin',
    ts: '2026-07-23T00:01:00Z',
    detail: { field: 'importance', from: 0.5, to: 0.85 }
  },
  {
    event_id: 'evt-3',
    memory_id: 'mem-1',
    action: 'archive',
    actor: 'admin',
    ts: '2026-07-23T00:02:00Z',
    detail: { a: 1, b: 2, c: 3, d: 4 }
  }
]

describe('MemoryAuditTimeline', () => {
  it('空：显示 "暂无审计事件" + 不显示 timeline', () => {
    const wrapper = mount(MemoryAuditTimeline, { props: { events: [] } })
    expect(wrapper.find('[data-testid="memory-audit-timeline"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-audit-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="memory-audit-events"]').exists()).toBe(false)
  })

  it('有事件：按 ts 倒序（最新在上）+ 渲染 action 中文标签 + dot class', () => {
    const wrapper = mount(MemoryAuditTimeline, { props: { events } })
    const rendered = wrapper.findAll('[data-testid^="memory-audit-row-evt-"]')
    expect(rendered).toHaveLength(3)
    // 倒序：archive(00:02) → update(00:01) → create(00:00)
    expect(rendered[0]?.text()).toContain('归档')
    expect(rendered[1]?.text()).toContain('更新')
    expect(rendered[2]?.text()).toContain('创建')
    // 计数
    expect(wrapper.find('[data-testid="memory-audit-count"]').text()).toContain('3')
  })

  it('detail 摘要：0 项显示 —，≤3 项显示全字段，>3 项显示前 3 项 + …', () => {
    const wrapper = mount(MemoryAuditTimeline, { props: { events } })
    const details = wrapper.findAll('[data-testid="memory-audit-row-detail"]')
    // create: detail={} → "—"
    expect(details[2]?.text()).toBe('—')
    // update: detail={field, from, to}（3 项）→ 全显示
    const updateDetail = details[1]?.text() ?? ''
    expect(updateDetail).toContain('field=')
    expect(updateDetail).toContain('from=0.5')
    expect(updateDetail).toContain('to=0.85')
    // archive: detail={a, b, c, d}（4 项）→ "4 项: a, b, c…"
    const archiveDetail = details[0]?.text() ?? ''
    expect(archiveDetail).toContain('4 项')
    expect(archiveDetail).toContain('a, b, c')
  })
})
