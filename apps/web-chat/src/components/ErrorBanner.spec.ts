// ErrorBanner 组件测试
// 2 个场景：空时不渲染 / 非空时渲染并触发 dismiss/clear 事件

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ErrorBanner from './ErrorBanner.vue'
import type { AppError } from '../composables/useErrorHandler'

describe('ErrorBanner', () => {
  it('空列表：组件不渲染（hasErrors=false）', () => {
    const w = mount(ErrorBanner, { props: { errors: [] as AppError[] } })
    expect(w.find('[data-testid="error-banner"]').exists()).toBe(false)
  })

  it('非空：渲染列表；每条带关闭按钮 + 清空全部；emit dismiss(i) / clear()', async () => {
    const errs: AppError[] = [
      { category: 'api', message: 'GET 500', code: 'E_API', ts: Date.now() - 1000 },
      { category: 'ws', message: 'connection lost', ts: Date.now() },
      { category: 'business', message: 'route failed', ts: Date.now() }
    ]
    const w = mount(ErrorBanner, { props: { errors: errs } })
    const banner = w.find('[data-testid="error-banner"]')
    expect(banner.exists()).toBe(true)

    const list = w.find('[data-testid="error-list"]')
    expect(list.exists()).toBe(true)
    const items = w.findAll('[data-testid^="error-item-"]')
    expect(items.length).toBe(3)
    expect(items[0]?.attributes('data-category')).toBe('api')
    expect(items[1]?.attributes('data-category')).toBe('ws')
    expect(items[2]?.attributes('data-category')).toBe('business')
    expect(items[0]?.text()).toContain('GET 500')
    expect(items[0]?.text()).toContain('E_API')

    // 关闭第 1 条
    await w.find('[data-testid="error-dismiss-0"]').trigger('click')
    expect(w.emitted('dismiss')).toBeTruthy()
    expect(w.emitted('dismiss')![0]).toEqual([0])

    // 清空全部
    await w.find('[data-testid="error-clear-all"]').trigger('click')
    expect(w.emitted('clear')).toBeTruthy()
  })
})
