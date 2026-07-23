"""FastAPI Depends 注入（runtime + ws_bridge 复用）。

设计：
- `get_runtime(request)` 优先返回测试注入的 fake runtime；否则构造 RuntimeAdapter
  并连接 kivi-core 守护进程（lifespan 阶段启用）
- `get_ws_bridge(request, runtime)` 懒构造 WebSocketBridge 并缓存到 app.state
- 单元测试用 `create_app(runtime=fake)` 注入，避免真实依赖
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kivi_agent.core.gateway.adapter import RuntimeAdapter
from kivi_agent.core.gateway.runtime import AgentRuntime
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge
from kivi_agent.core.transport.socket_client import SocketClient

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


# 提取 AgentRuntime（测试时直接注入；生产时由 lifespan 创建 RuntimeAdapter）
def get_runtime(request: Request) -> AgentRuntime:
    state = request.app.state
    injected: AgentRuntime | None = getattr(state, "injected_runtime", None)
    if injected is not None:
        return injected
    # 生产路径：构造 RuntimeAdapter 连接到 kivi-core 守护进程
    host: str = getattr(state, "core_host", "127.0.0.1")
    port: int = getattr(state, "core_port", 7437)
    client = SocketClient(host, port)
    # 不在 import 阶段 connect；调用方负责（lifespan 阶段会 connect）
    adapter = RuntimeAdapter(client)
    state.injected_runtime = adapter
    return adapter


# 懒构造 WebSocketBridge 并缓存到 app.state
def get_ws_bridge(request: Request, *, runtime: AgentRuntime) -> WebSocketBridge:
    state = request.app.state
    bridge: WebSocketBridge | None = getattr(state, "ws_bridge", None)
    if bridge is None:
        bridge = WebSocketBridge(runtime=runtime)
        state.ws_bridge = bridge
    return bridge


# 顶层辅助：直接拿 state 时（WS 路由无 Request Depends）使用
def get_runtime_from_state(state: Any) -> AgentRuntime:
    injected: AgentRuntime | None = getattr(state, "injected_runtime", None)
    if injected is not None:
        return injected
    host: str = getattr(state, "core_host", "127.0.0.1")
    port: int = getattr(state, "core_port", 7437)
    client = SocketClient(host, port)
    adapter = RuntimeAdapter(client)
    state.injected_runtime = adapter
    return adapter


def get_ws_bridge_from_state(
    state: Any, *, runtime: AgentRuntime
) -> WebSocketBridge:
    bridge: WebSocketBridge | None = getattr(state, "ws_bridge", None)
    if bridge is None:
        bridge = WebSocketBridge(runtime=runtime)
        state.ws_bridge = bridge
    return bridge
