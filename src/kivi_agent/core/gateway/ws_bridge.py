"""WebSocketBridge — 把 EventBus / Adapter 事件流转发到 WebSocket 客户端。

设计要点（D 报告 §迁移矩阵 4 + 12 + 关键约束）：
- 每个 WebSocket 客户端有**独立** `asyncio.Queue`。
  共用单一队列会让先到的 response 被后到的覆盖，导致 request_id 错配。
- 6 个新事件（LlmThinking / ChartRendered / RagSourcesCited /
  FrontendToolCallRequested / FrontendToolCallResponded / RunCancelled）
  走与 26 个现有事件完全相同的路由路径，按 session_id 路由。
- 客户端断开时，订阅者协程 + queue 自动清理。

使用方式（FastAPI 路由层）：
    bridge = WebSocketBridge(runtime=adapter)
    async with bridge.connect(session_id) as stream:
        async for event in stream:
            await ws.send_json(event)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from kivi_agent.core.gateway.runtime import AgentRuntime

logger = logging.getLogger(__name__)


@dataclass
class _ClientHandle:
    """单个 WebSocket 客户端的订阅句柄。"""

    session_id: str
    queue: asyncio.Queue[dict[str, Any]]


class WebSocketBridge:
    """WebSocket 事件桥接器。

    提供 `connect(session_id)` 上下文管理器，返回独立的事件流 AsyncIterator。
    每个 client 一个 queue，互不干扰。
    """

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime
        # session_id → 当前活跃的 client 句柄列表
        self._clients: dict[str, list[_ClientHandle]] = {}

    # 注册一个新 client handle；返回 (handle, AsyncIterator)
    def connect(self, session_id: str) -> "_Connection":
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        handle = _ClientHandle(session_id=session_id, queue=queue)
        self._clients.setdefault(session_id, []).append(handle)
        return _Connection(self, handle, session_id)

    # 客户端断开时移除 handle
    def _disconnect(self, handle: _ClientHandle) -> None:
        clients = self._clients.get(handle.session_id)
        if clients is None:
            return
        try:
            clients.remove(handle)
        except ValueError:
            return
        if not clients:
            self._clients.pop(handle.session_id, None)

    # 把事件 dict 推送到所有匹配 session 的 client queue
    async def publish(self, event: dict[str, Any]) -> None:
        session_id = self._extract_session_id(event)
        if session_id is None:
            return
        clients = list(self._clients.get(session_id, []))
        for client in clients:
            # put_nowait 而非 await put：避免单 client 慢消费阻塞其他 client
            try:
                client.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "ws_bridge: client queue full, dropping event for session=%s",
                    session_id,
                )

    # 从事件 dict 提取 session_id；6 个新事件 + 现有 session.* 事件都带 session_id
    @staticmethod
    def _extract_session_id(event: dict[str, Any]) -> str | None:
        sid = event.get("session_id")
        if isinstance(sid, str):
            return sid
        return None

    # 当前活跃连接数（用于测试 / 监控）
    def active_connections(self) -> int:
        return sum(len(v) for v in self._clients.values())


class _Connection:
    """WebSocket 客户端连接上下文管理器。

    使用：
        async with bridge.connect(session_id) as conn:
            async for event in conn.events():
                await ws.send_json(event)
    """

    def __init__(
        self,
        bridge: WebSocketBridge,
        handle: _ClientHandle,
        session_id: str,
    ) -> None:
        self._bridge = bridge
        self._handle = handle
        self._session_id = session_id
        self._closed = False

    async def __aenter__(self) -> _Connection:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    # 关闭连接，清理 bridge 内部状态
    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        # 推一个 sentinel 让 consumer 协程跳出
        with contextlib.suppress(asyncio.QueueFull):
            self._handle.queue.put_nowait(_SENTINEL_EVENT)
        self._bridge._disconnect(self._handle)

    # 异步事件流
    async def events(self) -> AsyncIterator[dict[str, Any]]:
        while not self._closed:
            event = await self._handle.queue.get()
            if event is _SENTINEL_EVENT:
                return
            yield event


# Sentinel 事件：客户端关闭时推入 queue，让 consumer 协程跳出
_SENTINEL_EVENT: dict[str, Any] = {"__sentinel__": True}
