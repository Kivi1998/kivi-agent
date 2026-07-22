"""T1: AgentRuntime Protocol 形状测试。

设计：
- Protocol 用鸭子类型；用具体 fake 实现验证 6 方法签名
- 重点验证返回类型（SessionInfo、AsyncIterator、Result 类型）形状
- SessionInfo 是 frozen dataclass，验证 immutability
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from kivi_agent.core.gateway.runtime import (
    AgentRuntime,
    Command,
    Event,
    Result,
    SessionInfo,
    SessionNotFoundError,
)


# 功能：SessionInfo 是 frozen dataclass，所有字段可访问且不可写
# 设计：构造后改字段必抛 FrozenInstanceError，证明上层使用安全
def test_session_info_frozen() -> None:
    info = SessionInfo(
        session_id="sess-1",
        user_id="u-1",
        goal="hello",
        created_at="2026-01-01T00:00:00Z",
        status="active",
        run_id=None,
    )
    assert info.session_id == "sess-1"
    assert info.run_id is None
    with pytest.raises((AttributeError, Exception)):
        info.session_id = "mutated"  # type: ignore[misc]


# 功能：SessionInfo 缺字段时 dataclass 构造失败
# 设计：省略必填字段触发 TypeError，证明字段定义明确
def test_session_info_required_fields() -> None:
    with pytest.raises(TypeError):
        SessionInfo(  # type: ignore[call-arg]
            session_id="sess-1", user_id="u-1",
        )


# 功能：FakeRuntime 实现 AgentRuntime 6 方法且类型可被调用
# 设计：用 concrete class 满足 Protocol；调用每个方法拿到对应返回值，证明
#       Protocol 结构可被 runtime_checkable / 鸭子类型消费
class FakeRuntime:
    """满足 AgentRuntime 形状的 fake；用于验证 Protocol 的可实现性。"""

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        return SessionInfo(
            session_id="sess-new",
            user_id=user_id,
            goal=goal,
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id="r-1",
        )

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        return True

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        return [
            SessionInfo(
                session_id="sess-1",
                user_id=user_id,
                goal="g",
                created_at="2026-01-01T00:00:00Z",
                status="active",
                run_id=None,
            )
        ]

    async def get_session(self, session_id: str) -> SessionInfo | None:
        if session_id == "missing":
            return None
        return SessionInfo(
            session_id=session_id,
            user_id="u-1",
            goal="g",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id=None,
        )

    async def send_command(self, session_id: str, command: Command) -> Result:
        # 简化：返回 command 自身当作 Result；Protocol 层只关心形状
        return command  # type: ignore[return-value]

    def subscribe_events(self, session_id: str) -> AsyncIterator[Event]:
        async def _gen() -> AsyncIterator[Event]:
            if False:
                yield  # type: ignore[unreachable]

        return _gen()


async def test_fake_runtime_satisfies_protocol() -> None:
    runtime: AgentRuntime = FakeRuntime()
    info = await runtime.start_session("u-1", "goal")
    assert info.session_id == "sess-new"
    assert info.status == "active"


async def test_fake_runtime_list_sessions() -> None:
    runtime: AgentRuntime = FakeRuntime()
    sessions = await runtime.list_sessions("u-1")
    assert len(sessions) == 1
    assert sessions[0].user_id == "u-1"


async def test_fake_runtime_get_session_missing_returns_none() -> None:
    runtime: AgentRuntime = FakeRuntime()
    assert await runtime.get_session("missing") is None
    info = await runtime.get_session("present")
    assert info is not None
    assert info.session_id == "present"


async def test_fake_runtime_cancel() -> None:
    runtime: AgentRuntime = FakeRuntime()
    assert await runtime.cancel_session("sess-1", "user clicked stop") is True


async def test_fake_runtime_send_command_roundtrip() -> None:
    """send_command 接受 Pydantic 命令模型并返回结果。"""
    runtime: AgentRuntime = FakeRuntime()
    from pydantic import BaseModel

    class PingCmd(BaseModel):
        type: str = "ping"

    result = await runtime.send_command("sess-1", PingCmd())
    assert result.type == "ping"


async def test_subscribe_events_returns_async_iterator() -> None:
    runtime: AgentRuntime = FakeRuntime()
    gen = runtime.subscribe_events("sess-1")
    # AsyncIterator 协议必须有 __aiter__/__anext__
    assert hasattr(gen, "__aiter__")
    assert hasattr(gen, "__anext__")


# 功能：SessionNotFoundError 携带 session_id 且可作为异常抛出
# 设计：验证异常字段在 HTTP 404 路径可被中间件读出
def test_session_not_found_error_carries_id() -> None:
    err = SessionNotFoundError("sess-404")
    assert err.session_id == "sess-404"
    with pytest.raises(SessionNotFoundError):
        raise err


# 功能：Protocol 形状正确（6 个方法 + 1 个 subscribe_events）
# 设计：反射检查 FakeRuntime 拥有 6 个方法名，证明契约面完整
def test_protocol_method_count() -> None:
    expected = {
        "start_session",
        "cancel_session",
        "list_sessions",
        "get_session",
        "send_command",
        "subscribe_events",
    }
    actual = set(dir(FakeRuntime()))
    assert expected.issubset(actual)


# 防止 import 警告
_ = Any
