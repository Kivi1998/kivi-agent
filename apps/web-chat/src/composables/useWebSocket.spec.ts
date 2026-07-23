// useWebSocket 状态机测试
// 5 个场景：connect / disconnect / reconnect / heartbeat / cleanup
//
// 使用 fake WebSocket 注入到 useWebSocket 构造器；
// jsdom 不支持原生 WebSocket，所以必须注入。

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { useWebSocket } from './useWebSocket'

/** 极简 fake WebSocket：暴露 onopen/onmessage/onclose/onerror 赋值 */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static reset(): void {
    FakeWebSocket.instances = []
  }
  static last(): FakeWebSocket | null {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1] ?? null
  }

  url: string
  readyState: number = 0
  sent: string[] = []
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onclose: ((ev?: Event) => void) | null = null
  onerror: ((ev?: Event) => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.closed = true
    // 模拟真实 close：同步触发 onclose
    this.onclose?.()
  }

  // ---- 测试辅助 ----

  /** 模拟服务端 accept */
  triggerOpen(): void {
    this.readyState = 1
    this.onopen?.()
  }

  /** 模拟服务端发消息 */
  triggerMessage(data: string | object): void {
    const payload = typeof data === 'string' ? data : JSON.stringify(data)
    this.onmessage?.({ data: payload } as MessageEvent)
  }

  /** 模拟服务端断线（无 explicit close） */
  triggerError(): void {
    this.onerror?.()
  }

  /** 模拟服务端 close（无 explicit close） */
  triggerRemoteClose(): void {
    this.onclose?.()
  }
}

function mountUseWebSocket(opts: {
  sessionId?: string
  onEvent?: (e: unknown) => void
  heartbeatInterval?: number
  heartbeatTimeout?: number
  initialReconnectDelay?: number
  maxReconnectDelay?: number
  onError?: (m: string) => void
  onReconnectAttempt?: (n: number) => void
} = {}) {
  const events: unknown[] = []
  const onEvent = opts.onEvent ?? ((e: unknown) => events.push(e))

  const Harness = defineComponent({
    setup() {
      const ws = useWebSocket(opts.sessionId ?? 'sess-1', {
        onEvent,
        WebSocketImpl: FakeWebSocket as unknown as { new (url: string): WebSocket },
        heartbeatInterval: opts.heartbeatInterval,
        heartbeatTimeout: opts.heartbeatTimeout,
        initialReconnectDelay: opts.initialReconnectDelay,
        maxReconnectDelay: opts.maxReconnectDelay,
        onError: opts.onError,
        onReconnectAttempt: opts.onReconnectAttempt
      })
      return { ws }
    },
    render() {
      return h('div', { 'data-state': this.ws.state.value })
    }
  })

  const wrapper = mount(Harness)
  return { wrapper, ws: wrapper.vm.ws, events }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    FakeWebSocket.reset()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('connect：connect() → 构造 WebSocket → onopen → state=open + 重置 attempts', async () => {
    const { ws } = mountUseWebSocket()
    // 初始未连接；调用 connect() 才开始
    expect(ws.state.value).toBe('connecting')
    expect(FakeWebSocket.instances.length).toBe(0)

    ws.connect()
    expect(FakeWebSocket.instances.length).toBe(1)
    expect(ws.state.value).toBe('connecting')

    const fake = FakeWebSocket.last()!
    fake.triggerOpen()
    await nextTick()
    expect(ws.state.value).toBe('open')
    expect(ws.reconnectAttempts.value).toBe(0)
  })

  it('disconnect：调用 close() → state=closed，不再自动重连', async () => {
    const { ws } = mountUseWebSocket()
    ws.connect()
    const fake = FakeWebSocket.last()!
    fake.triggerOpen()
    await nextTick()

    ws.close()
    await nextTick()
    expect(ws.state.value).toBe('closed')
    // 推进时间，确认没有新的 connect() 调用
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances.length).toBe(1)
  })

  it('reconnect：onclose 触发 → state=reconnecting → 指数退避后重连', async () => {
    const onReconnectAttempt = vi.fn()
    const { ws } = mountUseWebSocket({
      initialReconnectDelay: 100,
      maxReconnectDelay: 1_000,
      onReconnectAttempt
    })
    ws.connect()
    // 打开后断线
    const fake = FakeWebSocket.last()!
    fake.triggerOpen()
    await nextTick()

    // 模拟远端断线
    fake.triggerRemoteClose()
    await nextTick()
    expect(ws.state.value).toBe('reconnecting')
    expect(ws.reconnectAttempts.value).toBe(1)
    expect(onReconnectAttempt).toHaveBeenCalledWith(1)

    // 退避 100ms 后自动 reconnect
    vi.advanceTimersByTime(100)
    expect(FakeWebSocket.instances.length).toBe(2)
    const fake2 = FakeWebSocket.instances[1]!
    fake2.triggerOpen()
    await nextTick()
    expect(ws.state.value).toBe('open')
    expect(ws.reconnectAttempts.value).toBe(0)
  })

  it('heartbeat：定时发 ping；pong 更新 lastPongAt；超时主动 close', async () => {
    const onError = vi.fn()
    const { ws } = mountUseWebSocket({
      heartbeatInterval: 100,
      heartbeatTimeout: 500,
      initialReconnectDelay: 50,
      onError
    })
    ws.connect()
    const fake = FakeWebSocket.last()!
    fake.triggerOpen()
    await nextTick()

    // 第一拍：heartbeat 触发发 ping
    vi.advanceTimersByTime(100)
    const sentAfterFirst = fake.sent.filter((m) => m.includes('"ping"'))
    expect(sentAfterFirst.length).toBe(1)
    const firstPongTs = ws.lastPongAt.value
    expect(firstPongTs).not.toBeNull()

    // 服务端回 pong → lastPongAt 更新
    fake.triggerMessage({ type: 'pong' })
    await nextTick()
    expect(ws.lastPongAt.value).toBeGreaterThanOrEqual(firstPongTs!)

    // 模拟超时：再跳足够时间，期间没回 pong → close → reconnect
    // 心跳 100ms 一次，timeout 500ms → 第 6 次 tick（约 600ms）触发 close
    // 加上 initialReconnectDelay 50ms → 新连接应出现
    vi.advanceTimersByTime(800)
    expect(FakeWebSocket.instances.length).toBe(2)
  })

  it('cleanup：组件卸载时自动 close，不再持有连接', async () => {
    const { wrapper, ws } = mountUseWebSocket()
    ws.connect()
    const fake = FakeWebSocket.last()!
    fake.triggerOpen()
    await nextTick()

    wrapper.unmount()
    await nextTick()
    expect(ws.state.value).toBe('closed')
    // 卸载后再跳时间不会创建新连接
    vi.advanceTimersByTime(60_000)
    expect(FakeWebSocket.instances.length).toBe(1)
  })
})
