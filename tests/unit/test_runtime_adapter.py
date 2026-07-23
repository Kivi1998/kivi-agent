"""T2: RuntimeAdapter 6 方法测试（用 mock socket server 验证 IPC 路由）。

设计：
- 用 `asyncio.start_server` + port 0 启动内存中的 mock kivi-core，
  逐方法断言 IPC method 名 + params 正确；
- 不依赖真实 daemon；
- 6 个方法各覆盖 1+ 个测试。
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from kivi_agent.core.bus.commands import SessionCancelCommand
from kivi_agent.core.gateway.adapter import RuntimeAdapter
from kivi_agent.core.transport.socket_client import SocketClient

type Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _start_mock(handler: Handler) -> tuple[asyncio.AbstractServer, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


class _MockCore:
    """可注册的 mock kivi-core，记录所有收到的 RPC 请求。

    用法：
        core = _MockCore()
        core.register("session.create", lambda params: {"session_id": "sess-1", "status": "active"})
        server, port = await _start_mock(core.handle)
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

    def register(
        self, method: str, resp: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        self._handlers[method] = resp

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = msg.get("id")
            method = msg.get("method", "")
            params = msg.get("params", {})
            self.calls.append({"method": method, "params": params, "id": req_id})
            handler = self._handlers.get(method)
            if handler is None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
            else:
                result = handler(params)
                resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            writer.write(json.dumps(resp).encode() + b"\n")
            await writer.drain()


async def _make_adapter_and_loop() -> tuple[
    SocketClient, RuntimeAdapter, _MockCore, asyncio.AbstractServer, asyncio.Task[None]
]:
    """建立 mock core + SocketClient + RuntimeAdapter + 启动 event loop task。"""
    core = _MockCore()
    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)
    return client, adapter, core, server, loop_task


async def _teardown(
    client: SocketClient,
    server: asyncio.AbstractServer,
    loop_task: asyncio.Task[None],
) -> None:
    await client.close()
    server.close()
    try:
        await asyncio.wait_for(server.wait_closed(), timeout=1.0)
    except (TimeoutError, asyncio.CancelledError):
        pass
    loop_task.cancel()
    try:
        await loop_task
    except (asyncio.CancelledError, Exception):
        pass


# 功能：start_session 串行调 session.create + session.send_message，返回带 run_id 的 SessionInfo
# 设计：mock core 记录 method 调用，断言调用顺序 + 最终 SessionInfo 字段
async def test_start_session_invokes_create_and_send() -> None:
    core = _MockCore()
    core.register("session.create", lambda p: {"session_id": "sess-1", "status": "active"})
    core.register("session.send_message", lambda p: {"run_id": "r-99"})

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        info = await adapter.start_session("u-1", "build me a chart")
        assert info.session_id == "sess-1"
        assert info.run_id == "r-99"
        assert info.user_id == "u-1"
        assert info.goal == "build me a chart"
        assert info.status == "active"
        methods = [c["method"] for c in core.calls]
        assert methods == ["session.create", "session.send_message"]
        send_params = core.calls[1]["params"]
        assert send_params["session_id"] == "sess-1"
        assert send_params["content"] == "build me a chart"
    finally:
        await _teardown(client, server, loop_task)


# 功能：cancel_session 构造 SessionCancelCommand 并走通用 method dispatch
# 设计：mock core 提供 session.cancel 处理器；断言 method == "session.cancel" + params 完整
async def test_cancel_session_dispatches_session_cancel() -> None:
    core = _MockCore()
    core.register(
        "session.cancel",
        lambda p: {"cancelled": True, "session_id": p["session_id"], "ts": "2026-01-01T00:00:00Z"},
    )

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        ok = await adapter.cancel_session("sess-1", "user clicked stop")
        assert ok is True
        assert core.calls[0]["method"] == "session.cancel"
        params = core.calls[0]["params"]
        assert params["session_id"] == "sess-1"
        assert params["reason"] == "user clicked stop"
    finally:
        await _teardown(client, server, loop_task)


# 功能：cancel_session 在 core 未实现 session.cancel 时优雅返回 False
# 设计：mock core 不注册 session.cancel，模拟 A 阶段未实装；adapter 不抛错而是返回 False
async def test_cancel_session_method_not_found_returns_false() -> None:
    core = _MockCore()
    # 不注册 session.cancel

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        ok = await adapter.cancel_session("sess-1", "test")
        assert ok is False
    finally:
        await _teardown(client, server, loop_task)


# 功能：list_sessions 调 session.list 并把响应字段映射成 SessionInfo
# 设计：mock core 返回 2 个 session；断言解析后字段一致
async def test_list_sessions_returns_session_info_list() -> None:
    core = _MockCore()
    core.register(
        "session.list",
        lambda p: {
            "sessions": [
                {
                    "session_id": "sess-1",
                    "title": "g1",
                    "status": "active",
                    "created_at": "2026-01-01T00:00:00Z",
                    "last_run_id": "r-1",
                },
                {
                    "session_id": "sess-2",
                    "title": "g2",
                    "status": "closed",
                    "created_at": "2026-01-02T00:00:00Z",
                    "last_run_id": None,
                },
            ]
        },
    )

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        sessions = await adapter.list_sessions("u-1")
        assert len(sessions) == 2
        assert sessions[0].session_id == "sess-1"
        assert sessions[0].run_id == "r-1"
        assert sessions[1].status == "closed"
        assert core.calls[0]["method"] == "session.list"
        assert core.calls[0]["params"]["user_id"] == "u-1"
    finally:
        await _teardown(client, server, loop_task)


# 功能：list_sessions 在 core 未实现时返回空 list（A 阶段未实装）
# 设计：mock core 不注册 session.list；不抛错而是 []
async def test_list_sessions_method_not_found_returns_empty() -> None:
    core = _MockCore()

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        sessions = await adapter.list_sessions("u-1")
        assert sessions == []
    finally:
        await _teardown(client, server, loop_task)


# 功能：get_session 存在时返回 SessionInfo，不存在时返回 None
# 设计：mock core 区分 session.get_history 成功 vs 失败
async def test_get_session_returns_info_when_exists() -> None:
    core = _MockCore()
    core.register("session.get_history", lambda p: {"messages": []})

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        info = await adapter.get_session("sess-1")
        assert info is not None
        assert info.session_id == "sess-1"
    finally:
        await _teardown(client, server, loop_task)


async def test_get_session_returns_none_when_missing() -> None:
    # get_history 返回 SESSION_NOT_FOUND
    async def handle_history(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while True:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("method") == "session.get_history":
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32010, "message": "session not found"},
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": "unknown"},
                }
            writer.write(json.dumps(resp).encode() + b"\n")
            await writer.drain()

    server, port = await _start_mock(handle_history)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        info = await adapter.get_session("sess-missing")
        assert info is None
    finally:
        await _teardown(client, server, loop_task)


# 功能：send_command 通用 dispatch：按 command.type 作为 method + 把 params 整体发出去
# 设计：传入任意 BaseModel 子类，断言 mock core 收到正确 method
async def test_send_command_dispatches_by_type() -> None:
    core = _MockCore()
    core.register(
        "session.cancel",
        lambda p: {"cancelled": True, "session_id": p["session_id"], "ts": "t"},
    )

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        cmd = SessionCancelCommand(session_id="sess-1", reason="r")
        result = await adapter.send_command("sess-1", cmd)
        # 强转为 SessionCancelResult
        assert result.cancelled is True
        assert result.session_id == "sess-1"
        assert core.calls[0]["method"] == "session.cancel"
    finally:
        await _teardown(client, server, loop_task)


# 功能：send_command 缺 type 字段时抛 ValueError
# 设计：BaseModel 没 type 字段会 raise；保护 IPC 路由
async def test_send_command_rejects_invalid_command() -> None:
    core = _MockCore()
    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        from pydantic import BaseModel

        class NoTypeCmd(BaseModel):
            foo: str = "bar"

        with pytest.raises(ValueError):
            await adapter.send_command("sess-1", NoTypeCmd())
    finally:
        await _teardown(client, server, loop_task)


# 功能：subscribe_events 是 AsyncIterator，能用 async for 消费
# 设计：mock core 处理 event.subscribe 成功；adapter 推 1 条事件进 queue
async def test_subscribe_events_yields_events() -> None:
    core = _MockCore()
    core.register("event.subscribe", lambda p: {"subscription_id": "sub-1", "replayed_count": 0})

    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        gen = adapter.subscribe_events("sess-1")
        events: list[dict[str, Any]] = []

        async def _consume() -> None:
            async for event in gen:
                events.append(event)
                if len(events) >= 1:
                    break

        consumer = asyncio.create_task(_consume())
        # 等待 consumer 推进到第一个 await（send_command 完成）
        for _ in range(50):
            await asyncio.sleep(0.01)
            if "sess-1" in adapter._queues and adapter._queues["sess-1"]:
                break
        # 此时 adapter 内部 queue 已创建,推 1 条事件
        assert "sess-1" in adapter._queues
        await adapter._queues["sess-1"][0].put(
            {"type": "llm.token", "run_id": "r-1", "token": "hi", "ts": "t"}
        )
        await asyncio.wait_for(consumer, timeout=2.0)
        assert len(events) == 1
        assert events[0]["type"] == "llm.token"
    finally:
        await _teardown(client, server, loop_task)


# 功能：start_session 后只带 run_id 的事件（如 LlmTokenEvent）也能正确路由到对应 session WebSocket 客户端
# 设计：直接调 _on_socket_event 推 LlmTokenEvent(run_id)，断言订阅者 queue 收到；
#  验证 run_id → session_id 映射生效，覆盖 D 报告"WebSocket 看不到流式过程"问题
async def test_run_id_only_events_routed_via_mapping() -> None:
    core = _MockCore()
    core.register("session.create", lambda p: {"session_id": "sess-x", "status": "active"})
    core.register("session.send_message", lambda p: {"run_id": "r-x"})
    core.register("event.subscribe", lambda p: {"subscription_id": "sub-x", "replayed_count": 0})
    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        info = await adapter.start_session("u-1", "hi")
        assert info.session_id == "sess-x"
        assert info.run_id == "r-x"
        # 验证映射已建立
        assert adapter._run_to_session["r-x"] == "sess-x"

        # 启动订阅者
        events: list[dict[str, object]] = []

        async def _consume() -> None:
            async for ev in adapter.subscribe_events("sess-x"):
                events.append(ev)
                if len(events) >= 1:
                    break

        consumer = asyncio.create_task(_consume())
        # 等 queue 创建
        for _ in range(50):
            await asyncio.sleep(0.01)
            if "sess-x" in adapter._queues and adapter._queues["sess-x"]:
                break

        # 推一条**只带 run_id**的事件（Core 真实事件格式）
        await adapter._on_socket_event(
            {"type": "llm.token", "run_id": "r-x", "token": "world", "ts": "t2"}
        )
        await asyncio.wait_for(consumer, timeout=2.0)

        # WebSocket 客户端应能收到（不是 None / 不是空）
        assert len(events) == 1
        assert events[0]["type"] == "llm.token"
        assert events[0]["token"] == "world"
        assert events[0]["run_id"] == "r-x"
    finally:
        await _teardown(client, server, loop_task)


# 功能：run_id 映射外的孤儿事件（未在 _run_to_session 表中）不会路由到任何 session
# 设计：保护机制；避免错把别人的事件投递给当前 session
async def test_orphan_run_id_event_dropped() -> None:
    core = _MockCore()
    core.register("session.create", lambda p: {"session_id": "sess-y", "status": "active"})
    core.register("session.send_message", lambda p: {"run_id": "r-y"})
    core.register("event.subscribe", lambda p: {"subscription_id": "sub-y", "replayed_count": 0})
    server, port = await _start_mock(core.handle)
    client = SocketClient("127.0.0.1", port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    adapter = RuntimeAdapter(client)

    try:
        info = await adapter.start_session("u-2", "hi")
        assert info.run_id == "r-y"

        events: list[dict[str, object]] = []

        async def _consume() -> None:
            async for ev in adapter.subscribe_events("sess-y"):
                events.append(ev)
                if len(events) >= 1:
                    break

        consumer = asyncio.create_task(_consume())
        for _ in range(50):
            await asyncio.sleep(0.01)
            if "sess-y" in adapter._queues and adapter._queues["sess-y"]:
                break

        # 推一条 r-orphan 的事件（不在映射表里）
        await adapter._on_socket_event(
            {"type": "llm.token", "run_id": "r-orphan", "token": "x", "ts": "t"}
        )
        # 订阅者不应收到任何事件（timeout 内 consumer 没东西）
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(consumer, timeout=0.3)
        assert events == []
    finally:
        await _teardown(client, server, loop_task)
