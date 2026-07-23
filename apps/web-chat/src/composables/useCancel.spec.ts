// useCancel 测试
// 3 个场景：成功取消 / 失败 / 重入保护

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useCancel } from './useCancel'
import type { SessionApi } from '../api/session'
import type { CancelResponse } from '../types/api'

function makeApi(overrides: Partial<SessionApi> = {}): SessionApi {
  return {
    startSession: vi.fn(),
    getSession: vi.fn(),
    listSessions: vi.fn(),
    cancelSession: vi.fn(),
    request: vi.fn(),
    ...overrides
  }
}

function mountUseCancel(opts: { api: SessionApi; onError?: (m: string) => void }) {
  let apiRef: ReturnType<typeof useCancel> | null = null
  const Harness = defineComponent({
    setup() {
      apiRef = useCancel({ api: opts.api, onError: opts.onError })
      return { c: apiRef }
    },
    render() {
      return h('div')
    }
  })
  const wrapper = mount(Harness)
  return { wrapper, get c() { return apiRef! } }
}

describe('useCancel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('成功：调用 cancel → cancelSession 触发；isCancelling 复位；lastCancelledId 写入', async () => {
    const okResp: CancelResponse = {
      cancelled: true,
      session_id: 'sess-A',
      ts: '2026-07-23T00:00:00Z'
    }
    const api = makeApi({
      cancelSession: vi.fn().mockResolvedValue(okResp)
    })
    const { c } = mountUseCancel({ api })
    expect(c.isCancelling.value).toBe(false)

    const promise = c.cancel('sess-A', 'user pressed stop')
    // 调用期间 isCancelling = true
    expect(c.isCancelling.value).toBe(true)
    const ok = await promise
    expect(ok).toBe(true)
    expect(api.cancelSession).toHaveBeenCalledWith('sess-A', 'user pressed stop')
    expect(c.isCancelling.value).toBe(false)
    expect(c.lastError.value).toBeNull()
    expect(c.lastCancelledId.value).toBe('sess-A')
    expect(c.lastCancelledAt.value).not.toBeNull()
  })

  it('失败：cancelSession reject → lastError 写入 + onError 触发', async () => {
    const api = makeApi({
      cancelSession: vi.fn().mockRejectedValue(new Error('network down'))
    })
    const onError = vi.fn()
    const { c } = mountUseCancel({ api, onError })
    const ok = await c.cancel('sess-B', 'timeout')
    expect(ok).toBe(false)
    expect(c.isCancelling.value).toBe(false)
    expect(c.lastError.value).toBe('network down')
    expect(onError).toHaveBeenCalledWith('network down')
    expect(c.lastCancelledId.value).toBeNull()
  })

  it('重入：第二次调用会复盖 lastCancelledId；clearError 清空错误', async () => {
    const api = makeApi({
      cancelSession: vi
        .fn()
        .mockResolvedValueOnce({
          cancelled: true,
          session_id: 'sess-X',
          ts: ''
        })
        .mockResolvedValueOnce({
          cancelled: true,
          session_id: 'sess-Y',
          ts: ''
        })
    })
    const { c } = mountUseCancel({ api })
    await c.cancel('sess-X')
    await c.cancel('sess-Y')
    expect(c.lastCancelledId.value).toBe('sess-Y')
    expect(c.lastCancelledAt.value).not.toBeNull()

    // clearError
    ;(api.cancelSession as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('boom')
    )
    await c.cancel('sess-Z')
    expect(c.lastError.value).toBe('boom')
    c.clearError()
    expect(c.lastError.value).toBeNull()
  })
})
