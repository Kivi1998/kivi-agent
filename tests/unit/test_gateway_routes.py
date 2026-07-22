"""T4: FastAPI Gateway 6 路由 stub 测试。

设计：
- 用 `fastapi.testclient.TestClient` 验证 6 个路由的请求/响应 schema
- 注入 fake `AgentRuntime`（实现 6 方法），避免依赖真实 kivi-core
- 不测试 WebSocket 端到端（T3 已覆盖 WebSocketBridge 行为）
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from kivi_agent.core.gateway.runtime import SessionInfo, SessionNotFoundError  # noqa: E402
from kivi_agent.gateway.main import create_app  # noqa: E402


class FakeRuntime:
    """满足 AgentRuntime 6 方法的 fake；用于 TestClient 注入。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.start_return = SessionInfo(
            session_id="sess-new",
            user_id="u-1",
            goal="build a chart",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id="r-1",
        )
        self.list_return: list[SessionInfo] = []
        self.get_return: SessionInfo | None = None
        self.send_return: Any = {"ok": True}

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        self.calls.append(("start_session", {"user_id": user_id, "goal": goal}))
        return self.start_return

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        self.calls.append(("cancel_session", {"session_id": session_id, "reason": reason}))
        return True

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        self.calls.append(("list_sessions", {"user_id": user_id}))
        return self.list_return

    async def get_session(self, session_id: str) -> SessionInfo | None:
        self.calls.append(("get_session", {"session_id": session_id}))
        return self.get_return

    async def send_command(self, session_id: str, command: Any) -> Any:
        self.calls.append(("send_command", {"session_id": session_id, "command": command}))
        return self.send_return

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


# 功能：GET /health 返回 {"status": "ok", "version": "0.0.1"}
# 设计：基础健康检查；端到端联调时探活用
def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.0.1"


# 功能：POST /sessions 调用 start_session 并返回 201 + SessionInfoResponse
# 设计：请求体 {user_id, goal} 必填；响应 schema 校验
def test_post_sessions_creates_session(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    resp = client.post(
        "/sessions",
        json={"user_id": "u-1", "goal": "build a chart"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == "sess-new"
    assert body["user_id"] == "u-1"
    assert body["status"] == "active"
    assert body["run_id"] == "r-1"
    # 验证 fake runtime 被调
    method, params = fake_runtime.calls[0]
    assert method == "start_session"
    assert params == {"user_id": "u-1", "goal": "build a chart"}


# 功能：POST /sessions 缺字段时返回 422（Pydantic 自动校验）
# 设计：FastAPI Pydantic 校验是 contract 的第一道防线
def test_post_sessions_missing_fields_returns_422(client: TestClient) -> None:
    resp = client.post("/sessions", json={"user_id": "u-1"})  # 缺 goal
    assert resp.status_code == 422


# 功能：GET /sessions/{session_id} 存在时返回 SessionInfo
# 设计：fake runtime 返回 SessionInfo；响应 schema 校验
def test_get_session_returns_info(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.get_return = SessionInfo(
        session_id="sess-1",
        user_id="u-1",
        goal="g",
        created_at="2026-01-01T00:00:00Z",
        status="active",
        run_id="r-1",
    )
    resp = client.get("/sessions/sess-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "sess-1"
    assert body["run_id"] == "r-1"


# 功能：GET /sessions/{session_id} 不存在时返回 404
# 设计：fake runtime 返回 None → HTTPException 404
def test_get_session_not_found_returns_404(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.get_return = None
    resp = client.get("/sessions/sess-missing")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


# 功能：GET /sessions?user_id=... 调用 list_sessions 并返回 SessionListResponse
# 设计：query string 传 user_id；空列表时 sessions=[]
def test_list_sessions_returns_list(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.list_return = [
        SessionInfo(
            session_id="sess-1",
            user_id="u-1",
            goal="g1",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id=None,
        ),
        SessionInfo(
            session_id="sess-2",
            user_id="u-1",
            goal="g2",
            created_at="2026-01-02T00:00:00Z",
            status="closed",
            run_id=None,
        ),
    ]
    resp = client.get("/sessions?user_id=u-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u-1"
    assert len(body["sessions"]) == 2
    assert body["sessions"][0]["session_id"] == "sess-1"


# 功能：GET /sessions 缺 user_id 返回 422
# 设计：user_id 是必填 query
def test_list_sessions_missing_user_id_returns_422(client: TestClient) -> None:
    resp = client.get("/sessions")
    assert resp.status_code == 422


# 功能：POST /sessions/{session_id}/cancel 构造 SessionCancelCommand 调 send_command
# 设计：T5 集成；当前测试只验证 send_command 被调 + reason 字段透传
def test_cancel_session_invokes_send_command_with_session_cancel(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    from datetime import UTC, datetime

    fake_runtime.send_return = {
        "cancelled": True,
        "session_id": "sess-1",
        "ts": datetime.now(UTC).isoformat(),
    }
    resp = client.post(
        "/sessions/sess-1/cancel",
        json={"reason": "user clicked stop"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is True
    assert body["session_id"] == "sess-1"
    assert "ts" in body
    # 验证 send_command 被调（构造 SessionCancelCommand）
    method, params = fake_runtime.calls[0]
    assert method == "send_command"
    assert params["session_id"] == "sess-1"
    cmd = params["command"]
    assert cmd.type == "session.cancel"
    assert cmd.reason == "user clicked stop"
    assert cmd.session_id == "sess-1"


# 功能：POST /sessions/{session_id}/commands 通用命令入口
# 设计：request body {command: {type, ...}}；type 缺失返回 400
def test_send_command_dispatches_to_runtime(
    client: TestClient, fake_runtime: FakeRuntime
) -> None:
    fake_runtime.send_return = {"custom": "result"}
    resp = client.post(
        "/sessions/sess-1/commands",
        json={"command": {"type": "session.cancel", "session_id": "sess-1", "reason": "x"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "sess-1"
    assert body["result"] == {"custom": "result"}


# 功能：POST /sessions/{session_id}/commands 缺 type 字段返回 400
# 设计：缺少 type 无法路由到 IPC method
def test_send_command_missing_type_returns_400(client: TestClient) -> None:
    resp = client.post(
        "/sessions/sess-1/commands",
        json={"command": {"foo": "bar"}},
    )
    assert resp.status_code == 400
    assert "type" in resp.json()["detail"]


# 功能：WS 路由可被注册（不深入测试客户端连接逻辑）
# 设计：TestClient 的 websocket_connect 可用；此处仅断言路由存在
def test_websocket_route_registered(fake_runtime: FakeRuntime) -> None:
    app = create_app(runtime=fake_runtime)
    ws_routes = [
        route for route in app.routes
        if getattr(route, "path", "").endswith("/ws")
    ]
    assert len(ws_routes) == 1
    assert "/sessions/{session_id}/ws" in ws_routes[0].path


# 功能：所有 6 路由都被注册
# 设计：路由清单完整性
def test_all_six_routes_registered(fake_runtime: FakeRuntime) -> None:
    app = create_app(runtime=fake_runtime)
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    expected = {
        "/health",
        "/sessions",
        "/sessions/{session_id}",
        "/sessions/{session_id}/cancel",
        "/sessions/{session_id}/commands",
        "/sessions/{session_id}/ws",
    }
    assert expected.issubset(paths)


# 功能：未注入 runtime 时也能构造 app（生产路径占位）
# 设计：create_app(runtime=None) 走 lifespan / 真实 Adapter 路径
def test_create_app_without_injected_runtime() -> None:
    app = create_app(runtime=None)
    assert app.title == "kivi-agent Gateway"
    # deps.get_runtime 会在请求时构造 RuntimeAdapter（不连接）
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/sessions" in paths
