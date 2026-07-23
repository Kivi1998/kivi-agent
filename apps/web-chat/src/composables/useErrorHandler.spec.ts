// useErrorHandler 测试
// 4 个场景：report / 去重 / dismiss / clear + lastError computed

import { describe, expect, it } from 'vitest'
import { useErrorHandler } from './useErrorHandler'

describe('useErrorHandler', () => {
  it('report：上报 → errors 列表追加；hasErrors / lastError 反映最新', () => {
    const eh = useErrorHandler()
    expect(eh.hasErrors.value).toBe(false)
    expect(eh.lastError.value).toBeNull()

    eh.report({ category: 'api', message: 'GET /sessions 500' })
    expect(eh.errors.value.length).toBe(1)
    expect(eh.hasErrors.value).toBe(true)
    expect(eh.lastError.value?.message).toBe('GET /sessions 500')
    expect(eh.lastError.value?.category).toBe('api')

    eh.report({ category: 'ws', message: 'connection lost', code: 'WS_001' })
    expect(eh.errors.value.length).toBe(2)
    expect(eh.lastError.value?.category).toBe('ws')
    expect(eh.lastError.value?.code).toBe('WS_001')
  })

  it('去重：5s 内同 category + message 重复 report 不会追加', () => {
    const eh = useErrorHandler()
    eh.report({ category: 'business', message: 'route failed' })
    eh.report({ category: 'business', message: 'route failed' })
    eh.report({ category: 'business', message: 'route failed' })
    expect(eh.errors.value.length).toBe(1)

    // 不同 category 不会去重
    eh.report({ category: 'api', message: 'route failed' })
    expect(eh.errors.value.length).toBe(2)

    // 不同 message 不会去重
    eh.report({ category: 'business', message: 'route failed 2' })
    expect(eh.errors.value.length).toBe(3)
  })

  it('dismiss：按 index 删除单条；dismissCategory 按类清空', () => {
    const eh = useErrorHandler()
    eh.report({ category: 'api', message: 'm1' })
    eh.report({ category: 'ws', message: 'm2' })
    eh.report({ category: 'business', message: 'm3' })
    expect(eh.errors.value.length).toBe(3)

    eh.dismiss(1) // 删除 'm2'
    expect(eh.errors.value.length).toBe(2)
    expect(eh.errors.value.map((e) => e.message)).toEqual(['m1', 'm3'])

    // 越界 dismiss 安全 no-op
    eh.dismiss(99)
    expect(eh.errors.value.length).toBe(2)

    // 按类清空
    eh.dismissCategory('business')
    expect(eh.errors.value.length).toBe(1)
    expect(eh.errors.value[0]?.category).toBe('api')
  })

  it('clear：清空全部；超过 maxRetained 自动 FIFO 淘汰', () => {
    const eh = useErrorHandler({ maxRetained: 3 })
    for (let i = 0; i < 5; i++) {
      eh.report({ category: 'api', message: `m-${i}-${Date.now()}` })
      // 保证每条 5s 间隔，避免去重
    }
    expect(eh.errors.value.length).toBe(3)
    // FIFO：保留的是最后 3 条
    expect(eh.errors.value[0]?.message).toContain('m-2')
    expect(eh.errors.value[2]?.message).toContain('m-4')

    eh.clear()
    expect(eh.errors.value.length).toBe(0)
    expect(eh.hasErrors.value).toBe(false)
    expect(eh.lastError.value).toBeNull()
  })
})
