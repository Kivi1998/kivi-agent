// ConnectionStatus 组件测试
// 5 个场景：connecting / open / reconnecting / closed / error

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ConnectionStatus from './ConnectionStatus.vue'
import type { WSState } from '../composables/useWebSocket'

describe('ConnectionStatus', () => {
  it('connecting：testid + 黄色 + 文案', () => {
    const w = mount(ConnectionStatus, { props: { state: 'connecting' as WSState } })
    const el = w.find('[data-testid="connecting-status"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toMatch(/连接中/)
    expect(el.classes().join(' ')).toContain('text-accent-yellow')
  })

  it('open：testid + 绿色 + 文案', () => {
    const w = mount(ConnectionStatus, { props: { state: 'open' as WSState } })
    const el = w.find('[data-testid="connected-status"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toMatch(/已连接/)
    expect(el.classes().join(' ')).toContain('text-accent-green')
  })

  it('reconnecting：testid + 显示尝试次数', () => {
    const w = mount(ConnectionStatus, {
      props: { state: 'reconnecting' as WSState, reconnectAttempts: 3 }
    })
    const el = w.find('[data-testid="reconnecting-status"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toMatch(/重连中.*3/)
    expect(el.classes().join(' ')).toContain('text-accent-yellow')
  })

  it('closed：testid + 红色 + 文案', () => {
    const w = mount(ConnectionStatus, { props: { state: 'closed' as WSState } })
    const el = w.find('[data-testid="closed-status"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toMatch(/已断开/)
    expect(el.classes().join(' ')).toContain('text-accent-red')
  })

  it('error：testid + 红色 + 文案', () => {
    const w = mount(ConnectionStatus, { props: { state: 'error' as WSState } })
    const el = w.find('[data-testid="error-status"]')
    expect(el.exists()).toBe(true)
    expect(el.text()).toMatch(/错误/)
    expect(el.classes().join(' ')).toContain('text-accent-red')
  })
})
