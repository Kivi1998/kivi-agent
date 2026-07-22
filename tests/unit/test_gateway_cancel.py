"""T5: SessionCancel 命令在 Gateway 的集成测试。

设计：
- mock adapter + TestClient 验证 cancel 路由构造 SessionCancelCommand
  并正确解析 SessionCancelResult
- 覆盖正常路径、缺 reason 字段、result 是 dict 等边界情况
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from kivi_agent.core.gateway.runtime import SessionInfo  # noqa: E402
from kivi_agent.core.gateway.stub_protocol import (  # noqa: E402
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.gateway.main import create_app  # noqa: E402


class FakeRuntime:
    """满足 AgentRuntime 6 方法的 fake；记录 send_command 的 command。"""

    def __init__(self) -> None:
        self.send_command_calls: list[tuple[str, Any]] = []
        self.send_command_return: Any = None

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
        return []

    async def get_session(self, session_id: str) -> SessionInfo | None:
        return None

    async def send_command(self, session_id: str, command: Any) -> Any:
        self.send_command_calls.append((session_id, command))
        if self.send_command_return is not None:
            return self.send_command_return
        # 默认：返回 SessionCancelResult
        return SessionCancelResult(
            cancelled=True, session_id=session_id, ts="2026-01-01T00:00:00Z"
        )

    def subscribe_events(self, session_id: str) -> AsyncIterator[Any]:
        async def _gen() -> AsyncIterator[Any]:
            if False:
                yield  # type: ignore[unreachable]

        return _gen()


@pytest.fixture
def fake_runtime() -> FakeRuntime:
    return FakeRuntime()


@pytest.fixture
def client(fake_runtime: FakeRuntime):  # type: ignore[no-untyped-def]
    app = create_app(runtime=fake_runtime)
    with TestClient(app) as c:
        yield c


# 功能：POST /sessions/{id}/cancel 构造 SessionCancelCommand 并发送
# 设计：断言 send_command 被调 + command 是 SessionCancelCommand + fields 完整
def test_cancel_constructs_session_cancel_command(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    resp = client.post(
        "/sessions/sess-abc/cancel",
        json={"reason": "user pressed stop"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["session_id"] == "sess-abc"
    assert "ts" in body

    # 验证 send_command 被调 1 次,command 是 SessionCancelCommand
    assert len(fake_runtime.send_command_calls) == 1
    session_id_arg, cmd_arg = fake_runtime.send_command_calls[0]
    assert session_id_arg == "sess-abc"
    assert isinstance(cmd_arg, SessionCancelCommand)
    assert cmd_arg.session_id == "sess-abc"
    assert cmd_arg.reason == "user pressed stop"
    assert cmd_arg.type == "session.cancel"


# 功能：reason 字段缺省时仍可正常处理
# 设计：CancelRequest.reason 默认 ""，构造的 SessionCancelCommand.reason 也应为 ""
def test_cancel_without_reason_field(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    resp = client.post("/sessions/sess-abc/cancel", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["session_id"] == "sess-abc"

    session_id_arg, cmd_arg = fake_runtime.send_command_calls[0]
    assert cmd_arg.reason == ""


# 功能：result 是 dict 时仍能正确解析 cancelled + ts
# 设计：adapter 可能返回 dict（_DictResult 路径或 transport 直传），路由层兼容
def test_cancel_parses_dict_result(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.send_command_return = {
        "cancelled": True,
        "session_id": "sess-abc",
        "ts": "2026-02-01T00:00:00Z",
    }
    resp = client.post("/sessions/sess-abc/cancel", json={"reason": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["ts"] == "2026-02-01T00:00:00Z"


# 功能：result.cancelled = False 时正确反映
# 设计：用户多次 cancel 同一 session 时第二次可能返回 False
def test_cancel_returns_false_when_not_cancelled(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.send_command_return = SessionCancelResult(
        cancelled=False, session_id="sess-abc", ts="2026-03-01T00:00:00Z"
    )
    resp = client.post("/sessions/sess-abc/cancel", json={"reason": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is False


# 功能：response schema 严格匹配 CancelResponse
# 设计：cancelled / session_id / ts 三字段全在
def test_cancel_response_schema(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    resp = client.post("/sessions/sess-x/cancel", json={"reason": "x"})
    assert resp.status_code == 200
    body = resp.json()
    # 三字段
    assert set(body.keys()) == {"cancelled", "session_id", "ts"}


# 功能：reason 字段是空字符串时正常（与缺省等价）
# 设计：前端可能传 reason=""
def test_cancel_with_empty_reason(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    resp = client.post("/sessions/sess-x/cancel", json={"reason": ""})
    assert resp.status_code == 200
    session_id_arg, cmd_arg = fake_runtime.send_command_calls[0]
    assert cmd_arg.reason == ""


# 功能：reason 是非 str 类型时 Pydantic 自动校验失败（422）
# 设计：CancelRequest.reason 是 str 类型,传 int 会 422
def test_cancel_invalid_reason_type_returns_422(client: TestClient) -> None:
    resp = client.post("/sessions/sess-x/cancel", json={"reason": 123})
    assert resp.status_code == 422
