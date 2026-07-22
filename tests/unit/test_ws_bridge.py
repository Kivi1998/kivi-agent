"""T3: WebSocketBridge 测试。

设计：
- 2 客户端订阅同一 session，事件按 session_id 路由不串
- 6 个新事件（llm.thinking / chart.rendered / rag.sources_cited /
  frontend_tool.call_requested / frontend_tool.call_responded / run.cancelled）
  必须能正确路由
- 客户端断开后 queue 自动清理（D 报告：禁止共用单一队列错配响应）
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from kivi_agent.core.gateway.runtime import SessionInfo
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge


# 极简 fake AgentRuntime,只 stub subscribe_events 返回一个手动控制的生成器
class _FakeRuntime:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        raise NotImplementedError

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        return True

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        return []

    async def get_session(self, session_id: str) -> SessionInfo | None:
        return None

    async def send_command(self, session_id: str, command: Any) -> Any:
        raise NotImplementedError

    def subscribe_events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        async def _gen() -> AsyncIterator[dict[str, Any]]:
            # 不主动 yield, 由测试通过 push 事件
            while True:
                await asyncio.sleep(0.1)
                if False:
                    yield  # type: ignore[unreachable]

        return _gen()


# 功能：1 个客户端订阅 session，bridge.publish 把同 session 事件投递到该 client
# 设计：publish(带 session_id 事件) → client.events() 收到
async def test_single_client_receives_matching_event() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)

    async with bridge.connect("sess-1") as conn:
        await bridge.publish(
            {"type": "llm.token", "session_id": "sess-1", "token": "hi", "ts": "t"}
        )
        # 等待 1 个事件
        gen = conn.events()
        event = await asyncio.wait_for(anext(gen), timeout=1.0)
        assert event["type"] == "llm.token"
        await gen.aclose()


# helper for async iterator next
async def anext(it: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
    return await it.__anext__()


# 功能：2 客户端订阅同一 session，事件不串 — 各 client 独立 queue
# 设计：推 2 条事件，client A / B 各拿 2 条；并且顺序不依赖 publish 顺序（D 报告核心）
async def test_two_clients_same_session_no_cross_talk() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)

    async with bridge.connect("sess-1") as conn_a, bridge.connect("sess-1") as conn_b:
        gen_a = conn_a.events()
        gen_b = conn_b.events()
        # 推 2 条事件
        await bridge.publish({"type": "llm.token", "session_id": "sess-1", "token": "a"})
        await bridge.publish({"type": "llm.token", "session_id": "sess-1", "token": "b"})

        # client A 拿 2 条
        e_a1 = await asyncio.wait_for(anext(gen_a), timeout=1.0)
        e_a2 = await asyncio.wait_for(anext(gen_a), timeout=1.0)
        # client B 也拿 2 条（独立 queue 复制）
        e_b1 = await asyncio.wait_for(anext(gen_b), timeout=1.0)
        e_b2 = await asyncio.wait_for(anext(gen_b), timeout=1.0)

        # A 和 B 都收到 2 条；彼此内容一致
        assert e_a1["token"] == "a"
        assert e_a2["token"] == "b"
        assert e_b1["token"] == "a"
        assert e_b2["token"] == "b"

        await gen_a.aclose()
        await gen_b.aclose()


# 功能：2 客户端订阅不同 session，事件按 session_id 严格隔离
# 设计：推 sess-1 事件，sess-2 client 收不到
async def test_two_clients_different_sessions_isolated() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)

    async with bridge.connect("sess-1") as conn_1, bridge.connect("sess-2") as conn_2:
        gen_1 = conn_1.events()
        gen_2 = conn_2.events()

        await bridge.publish({"type": "llm.token", "session_id": "sess-1", "token": "for-1"})
        # client_1 应收到；client_2 不应收到
        e1 = await asyncio.wait_for(anext(gen_1), timeout=1.0)
        assert e1["token"] == "for-1"

        # client_2 在超时窗口内不应有事件
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(gen_2), timeout=0.2)

        await gen_1.aclose()
        await gen_2.aclose()


# 功能：6 个新事件都能正确路由（不漏接、不错配）
# 设计：构造 6 个 v1 §5.2.1 事件，按 session 推送
@pytest.mark.parametrize(
    "event_type",
    [
        "llm.thinking",
        "chart.rendered",
        "rag.sources_cited",
        "frontend_tool.call_requested",
        "frontend_tool.call_responded",
        "run.cancelled",
    ],
)
async def test_six_new_events_routed_correctly(event_type: str) -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)

    async with bridge.connect("sess-1") as conn:
        gen = conn.events()
        event = {
            "type": event_type,
            "session_id": "sess-1",
            "run_id": "r-1",
            "ts": "2026-01-01T00:00:00Z",
        }
        await bridge.publish(event)
        received = await asyncio.wait_for(anext(gen), timeout=1.0)
        assert received["type"] == event_type
        await gen.aclose()


# 功能：客户端断开后, bridge 内部清理（active_connections 减 1）
# 设计：connect → close → active_connections == 0
async def test_disconnect_cleans_up() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)
    assert bridge.active_connections() == 0
    async with bridge.connect("sess-1") as conn:
        assert bridge.active_connections() == 1
        # 推出但不消费
        await bridge.publish({"type": "x", "session_id": "sess-1"})
        _ = conn
    assert bridge.active_connections() == 0


# 功能：客户端断开时, 阻塞在 events() 的协程能跳出（不挂死）
# 设计：consumer 协程先阻塞在 queue.get(), close() 推 sentinel, events() 看到 sentinel 后 return
async def test_disconnect_unblocks_event_iterator() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)
    conn = bridge.connect("sess-1")
    gen = conn.events()

    consumer_done = asyncio.Event()

    async def _consume() -> None:
        async for _ in gen:  # pragma: no cover - consumer 阻塞
            pass
        consumer_done.set()

    consumer = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    # 此时 consumer 阻塞在 queue.get()
    await conn.close()
    # 等待 consumer 协程退出（sentinel 触发 events() return）
    await asyncio.wait_for(consumer_done.wait(), timeout=1.0)
    assert consumer.done()
    assert consumer.exception() is None
    await gen.aclose()


# 功能：多客户端断开后, sess-1 / sess-2 各自清空内部 map
# 设计：验证 _clients map 按 session_id 分桶
async def test_per_session_bucket_cleanup() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)
    async with bridge.connect("sess-1"):
        async with bridge.connect("sess-2"):
            assert bridge.active_connections() == 2
            assert set(bridge._clients.keys()) == {"sess-1", "sess-2"}
        # sess-2 关闭
        assert bridge.active_connections() == 1
        assert set(bridge._clients.keys()) == {"sess-1"}
    assert bridge.active_connections() == 0
    assert bridge._clients == {}


# 功能：event 没有 session_id 字段时, bridge 不投递（防御性）
# 设计：推无 session_id 事件, 没有任何 client 收到
async def test_event_without_session_id_dropped() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)
    async with bridge.connect("sess-1") as conn:
        gen = conn.events()
        # 推无 session_id 事件
        await bridge.publish({"type": "run.started", "run_id": "r-1", "ts": "t"})
        # 等待 0.2s 确认无投递
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(gen), timeout=0.2)
        await gen.aclose()
