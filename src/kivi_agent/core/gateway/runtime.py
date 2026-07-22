"""AgentRuntime 门面（Protocol）。

Wave 1 D 阶段为 Web 前端 / FastAPI Gateway 提供统一的 Runtime 抽象。
Adapter（`RuntimeAdapter`）将 kivi-core IPC 桥接到本 Protocol。

设计要点：
- 6 个方法 + 1 个事件订阅，全部使用 Protocol 描述，duck-typed；
- `Event` / `Command` / `Result` 是 Pydantic `BaseModel` 的 TypeVar，调用方按业务传入具体子类；
- 不在 Protocol 层硬编码 6 个新事件 / SessionCancel；调用方直接从
  `kivi_agent.core.bus.events` 和 `kivi_agent.core.bus.commands` 取 v1 §5.2 冻结的类型。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

# 事件 / 命令 / 结果的 Pydantic 模型占位泛型
Event = TypeVar("Event", bound=BaseModel)
Command = TypeVar("Command", bound=BaseModel)
Result = TypeVar("Result", bound=BaseModel)


@dataclass(frozen=True)
class SessionInfo:
    """Session 元数据（Web 前端用）。"""

    session_id: str
    user_id: str
    goal: str
    created_at: str  # ISO 8601
    status: str      # "active" | "waiting_for_input" | "closed"
    run_id: str | None = None


class SessionNotFoundError(LookupError):
    """请求的 session_id 不存在时抛出（adapter / gateway 层透传为 HTTP 404）。"""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session not found: {session_id}")
        self.session_id = session_id


class AgentRuntime(Protocol):
    """Gateway 侧的 Runtime 抽象。

    Adapter 实现本 Protocol，FastAPI 路由层只持有 AgentRuntime 引用，
    不直接 import `kivi_agent.core` 的任何具体类型。
    """

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        """创建并启动一个新 session。"""
        ...

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        """取消运行中的 session。返回是否成功取消。"""
        ...

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        """按 user_id 列出该用户的所有 session。"""
        ...

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """查询单个 session 元数据；不存在返回 None。"""
        ...

    async def send_command(self, session_id: str, command: Command) -> Result:
        """向 session 发送一个命令并等待结果。"""
        ...

    def subscribe_events(self, session_id: str) -> AsyncIterator[Event]:
        """订阅该 session 的事件流。"""
        ...
