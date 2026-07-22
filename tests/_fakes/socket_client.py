"""SocketClient 的 Fake 实现（IPC mock）。

为什么单独做 FakeSocketClient 而不是直接 mock：
- `SocketClient.send_command` 涉及 asyncio.Future / 异步流；用 mock 容易遗漏边界
- 单元测试需要可控的"服务器响应"+"事件推送"序列，Fake 提供
  `set_response(method, result)` 和 `push_event(event_dict)` 两个显式 API

边界：
- FakeSocketClient **不** 真实连接 socket；只提供与生产 SocketClient 同名的方法
- 调用方不应假设 `FakeSocketClient` 实现了 `_reader` / `_writer` 内部细节
- 如果测试需要真实 socket 行为，请用 `tests/integration/conftest.py::running_daemon`
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

type EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class FakeSocketClient:
    """SocketClient 替身，提供命令请求 → 响应 + 服务器推送事件能力。

    用法：
        client = FakeSocketClient(host="fake", port=0)
        await client.connect()
        client.set_response("ping", {"pong": True})
        result = await client.send_command("ping", {})  # → {"pong": True}
        await client.push_event({"type": "core.started", ...})
    """

    def __init__(self, host: str = "fake", port: int = 0) -> None:
        self._host = host
        self._port = port
        self._connected = False
        self._event_handlers: list[EventHandler] = []
        # method → 预设响应
        self._responses: dict[str, dict[str, Any] | Exception] = {}
        # 观测
        self.sent_commands: list[dict[str, Any]] = []
        self.connect_count: int = 0
        self.close_count: int = 0

    # 模拟 connect：仅设置标志位
    async def connect(self) -> None:
        self._connected = True
        self.connect_count += 1

    # 模拟 close
    async def close(self) -> None:
        self._connected = False
        self.close_count += 1

    # 注册事件回调
    def on_event(self, handler: EventHandler) -> None:
        self._event_handlers.append(handler)

    # 预设某 method 的响应（下次 send_command 同 method 时返回）
    def set_response(self, method: str, result: dict[str, Any]) -> None:
        self._responses[method] = result

    # 预设某 method 抛 IpcError
    def set_error(self, method: str, exc: Exception) -> None:
        self._responses[method] = exc

    # 模拟 send_command
    async def send_command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._connected:
            raise RuntimeError("not connected — call connect() first")
        req_id = str(uuid.uuid4())
        self.sent_commands.append({"id": req_id, "method": method, "params": params})
        # 取响应
        if method not in self._responses:
            raise KeyError(
                f"FakeSocketClient: 未预设 method={method!r} 的响应；"
                f"已预设: {list(self._responses)}"
            )
        resp = self._responses[method]
        if isinstance(resp, Exception):
            raise resp
        return resp

    # 模拟服务器主动推送事件
    async def push_event(self, event: dict[str, Any]) -> None:
        if not self._connected:
            raise RuntimeError("not connected — call connect() first")
        for handler in self._event_handlers:
            await handler(event)

    # 让测试断言已发送的命令
    def assert_called(self, method: str, *, count: int | None = None) -> None:
        actual = sum(1 for c in self.sent_commands if c["method"] == method)
        if count is None:
            assert actual >= 1, f"method={method!r} 未被调用"
        else:
            assert actual == count, f"method={method!r} 期望 {count} 次，实际 {actual} 次"

    # 兼容生产 SocketClient 的 run_event_loop（Fake 中无需读流，空实现）
    async def run_event_loop(self) -> None:
        # 永久挂起，让测试主动关闭
        await asyncio.Event().wait()

    # 重置所有状态
    def reset(self) -> None:
        self._responses = {}
        self.sent_commands = []
        self.connect_count = 0
        self.close_count = 0
        self._event_handlers = []
        self._connected = False
