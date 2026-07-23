// CancelButton 组件测试
// 2 个场景：idle 点击 emit cancel / isCancelling 时禁用 + 文案切换

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CancelButton from './CancelButton.vue'

describe('CancelButton', () => {
  it('idle：点击 → emit("cancel")；testid=cancel-button；data-session-id 写入', async () => {
    const w = mount(CancelButton, {
      props: { sessionId: 'sess-X', isCancelling: false }
    })
    const btn = w.find('[data-testid="cancel-button"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('data-session-id')).toBe('sess-X')
    expect(btn.attributes('data-cancelling')).toBe('false')
    expect(btn.text()).toContain('停止')
    expect(btn.attributes('disabled')).toBeUndefined()

    await btn.trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
    expect(w.emitted('cancel')!.length).toBe(1)
  })

  it('isCancelling：禁用 + testid=cancel-button-loading + 文案"取消中…"', async () => {
    const w = mount(CancelButton, {
      props: { sessionId: 'sess-Y', isCancelling: true }
    })
    const btn = w.find('[data-testid="cancel-button-loading"]')
    expect(btn.exists()).toBe(true)
    expect(btn.text()).toContain('取消中')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.attributes('data-cancelling')).toBe('true')

    // disabled 按钮 click 不会 emit（组件内 onClick 检查 isDisabled）
    await btn.trigger('click')
    expect(w.emitted('cancel')).toBeFalsy()
  })
})
