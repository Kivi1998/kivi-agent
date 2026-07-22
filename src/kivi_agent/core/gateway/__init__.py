"""kivi-agent Gateway 骨架（Wave 1 / D 阶段）。

本包提供 AgentRuntime 门面 + RuntimeAdapter + WebSocketBridge：
- `AgentRuntime` 是面向 Web 前端的 Protocol 定义；
- `RuntimeAdapter` 把现有 kivi-core IPC（SocketClient）封装为 AgentRuntime；
- `WebSocketBridge` 把 EventBus 事件流转发到 WebSocket 客户端。

FastAPI 路由层在 `kivi_agent.gateway.main`（顶层 gateway 目录）。
"""

from kivi_agent.core.gateway.adapter import RuntimeAdapter
from kivi_agent.core.gateway.runtime import (
    AgentRuntime,
    Command,
    Event,
    Result,
    SessionInfo,
    SessionNotFoundError,
)
from kivi_agent.core.gateway.stub_protocol import (
    ChartRenderedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge

__all__ = [
    "AgentRuntime",
    "ChartRenderedEvent",
    "Command",
    "Event",
    "FrontendToolCallRequested",
    "FrontendToolCallResponded",
    "LlmThinkingEvent",
    "RagSourcesCitedEvent",
    "Result",
    "RunCancelledEvent",
    "RuntimeAdapter",
    "SessionCancelCommand",
    "SessionCancelResult",
    "SessionInfo",
    "SessionNotFoundError",
    "WebSocketBridge",
]
