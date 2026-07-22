"""FastAPI Gateway 骨架（Wave 1 / D 阶段）。

提供 6 个 HTTP / WebSocket 路由 stub：
1. POST   /sessions                            — 创建并启动 session
2. GET    /sessions                            — 列出 user 的所有 session
3. GET    /sessions/{session_id}               — 查询单个 session
4. POST   /sessions/{session_id}/cancel        — 取消运行中的 session（T5 接入 SessionCancel）
5. POST   /sessions/{session_id}/commands      — 通用命令发送
6. WS     /sessions/{session_id}/ws            — 事件流（per-client queue）

FastAPI / uvicorn / websockets 是 dev optional 依赖：
- 顶层 `gateway.__init__` 暴露 `create_app`，本模块 import 时不强制依赖
- 调用方在使用前需先 `uv sync --group dev`
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from fastapi import (
        FastAPI,
        HTTPException,
        Request,
        WebSocket,
        WebSocketDisconnect,
        status,
    )
    from pydantic import BaseModel, Field
except ImportError as e:  # pragma: no cover - 由调用方处理
    raise ImportError(
        "kivi_agent.gateway 需要 fastapi 依赖。"
        "请先运行 `uv sync --group dev` 或 `uv pip install 'kivi-agent[gateway]'`。"
    ) from e

from kivi_agent.core.gateway.runtime import (
    AgentRuntime,
    SessionInfo,
)
from kivi_agent.core.bus.commands import (
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge
from kivi_agent.gateway.deps import (
    get_runtime,
    get_runtime_from_state,
    get_ws_bridge,
    get_ws_bridge_from_state,
)

logger = logging.getLogger(__name__)


# ---- Request / Response 模型 ----

class StartSessionRequest(BaseModel):
    """POST /sessions 请求体。"""

    user_id: str = Field(..., description="用户 ID,用于会话隔离")
    goal: str = Field(..., description="Agent 任务目标")


class SessionInfoResponse(BaseModel):
    """Session 元数据响应。"""

    session_id: str
    user_id: str
    goal: str
    created_at: str
    status: str
    run_id: str | None = None

    @classmethod
    def from_info(cls, info: SessionInfo) -> SessionInfoResponse:
        return cls(
            session_id=info.session_id,
            user_id=info.user_id,
            goal=info.goal,
            created_at=info.created_at,
            status=info.status,
            run_id=info.run_id,
        )


class SessionListResponse(BaseModel):
    """GET /sessions 响应。"""

    user_id: str
    sessions: list[SessionInfoResponse]


class CancelRequest(BaseModel):
    """POST /sessions/{session_id}/cancel 请求体。"""

    reason: str = Field(default="", description="取消原因")


class CancelResponse(BaseModel):
    """POST /sessions/{session_id}/cancel 响应。"""

    cancelled: bool
    session_id: str
    ts: str


class SendCommandRequest(BaseModel):
    """POST /sessions/{session_id}/commands 通用命令请求体。"""

    command: dict[str, Any] = Field(
        ...,
        description="Pydantic 命令 dict, 必须含 type 字段（决定 IPC method）",
    )


class SendCommandResponse(BaseModel):
    """POST /sessions/{session_id}/commands 响应。"""

    session_id: str
    result: dict[str, Any]


# ---- 应用工厂 ----

# kivi-core 守护进程地址（默认 127.0.0.1:7437，与 SocketServer 默认值一致）
DEFAULT_CORE_HOST = "127.0.0.1"
DEFAULT_CORE_PORT = 7437


# 创建 FastAPI 应用骨架
def create_app(
    runtime: AgentRuntime | None = None,
    *,
    core_host: str | None = None,
    core_port: int | None = None,
) -> FastAPI:
    """构造 FastAPI Gateway。

    参数：
    - `runtime`: 可选 AgentRuntime 实例（测试时注入 fake，生产由 lifespan 创建真实 Adapter）
    - `core_host` / `core_port`: 注入 kivi-core 守护进程地址（供 lifespan 创建 Adapter）
    """
    app = FastAPI(
        title="kivi-agent Gateway",
        version="0.0.1",
        description="Wave 1 / D 阶段骨架。FastAPI / uvicorn 是 dev optional 依赖。",
    )

    _host = core_host or os.environ.get("KAMA_HOST", DEFAULT_CORE_HOST)
    _port = core_port if core_port is not None else int(
        os.environ.get("KAMA_PORT", str(DEFAULT_CORE_PORT))
    )
    app.state.core_host = _host
    app.state.core_port = _port
    app.state.injected_runtime = runtime
    app.state.ws_bridge = None

    _register_routes(app)
    return app


# 注册全部路由 + health 端点
def _register_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.0.1"}

    @app.post(
        "/sessions",
        response_model=SessionInfoResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def start_session(
        req: StartSessionRequest,
        request: Request,
    ) -> SessionInfoResponse:
        """创建并启动新 session。"""
        runtime = get_runtime(request)
        info = await runtime.start_session(req.user_id, req.goal)
        return SessionInfoResponse.from_info(info)

    @app.get(
        "/sessions/{session_id}",
        response_model=SessionInfoResponse,
    )
    async def get_session(
        session_id: str,
        request: Request,
    ) -> SessionInfoResponse:
        """查询单个 session 元数据。"""
        runtime = get_runtime(request)
        info = await runtime.get_session(session_id)
        if info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"session not found: {session_id}",
            )
        return SessionInfoResponse.from_info(info)

    @app.get(
        "/sessions",
        response_model=SessionListResponse,
    )
    async def list_sessions(
        user_id: str,
        request: Request,
    ) -> SessionListResponse:
        """列出 user_id 的所有 session。

        Wave 1 阶段 user_id 通过 query string 传入（无鉴权）。
        阶段 8 收口时统一接入鉴权中间件。
        """
        runtime = get_runtime(request)
        sessions = await runtime.list_sessions(user_id)
        return SessionListResponse(
            user_id=user_id,
            sessions=[SessionInfoResponse.from_info(s) for s in sessions],
        )

    @app.post(
        "/sessions/{session_id}/cancel",
        response_model=CancelResponse,
    )
    async def cancel_session(
        session_id: str,
        req: CancelRequest,
        request: Request,
    ) -> CancelResponse:
        """取消运行中的 session（T5 接入 SessionCancelCommand）。"""
        from datetime import UTC, datetime

        runtime = get_runtime(request)
        cmd = SessionCancelCommand(session_id=session_id, reason=req.reason)
        result: Any = await runtime.send_command(session_id, cmd)
        ts: str
        if isinstance(result, SessionCancelResult):
            cancelled = result.cancelled
            ts = result.ts
        elif isinstance(result, BaseModel):
            cancelled = bool(getattr(result, "cancelled", False))
            ts = str(getattr(result, "ts", datetime.now(UTC).isoformat()))
        elif isinstance(result, dict):
            cancelled = bool(result.get("cancelled", False))
            ts = str(result.get("ts", datetime.now(UTC).isoformat()))
        else:
            cancelled = False
            ts = datetime.now(UTC).isoformat()
        return CancelResponse(cancelled=cancelled, session_id=session_id, ts=ts)

    @app.post(
        "/sessions/{session_id}/commands",
        response_model=SendCommandResponse,
    )
    async def send_command(
        session_id: str,
        req: SendCommandRequest,
        request: Request,
    ) -> SendCommandResponse:
        """通用命令发送。

        请求体 `command` 必须是含 `type` 字段的 Pydantic 命令 dict。
        """
        runtime = get_runtime(request)
        cmd_dict = req.command
        if "type" not in cmd_dict or not isinstance(cmd_dict["type"], str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="command.type must be a non-empty string",
            )
        if not cmd_dict["type"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="command.type must be a non-empty string",
            )

        # 动态构造一个 Pydantic 模型承载 dict（type 字段 + 透传其他字段）
        class _GenericCmd(BaseModel):
            model_config = {"extra": "allow"}

        cmd_obj = _GenericCmd.model_validate(cmd_dict)
        result: Any = await runtime.send_command(session_id, cmd_obj)
        # result 统一 dump
        if isinstance(result, BaseModel):
            result_dict = result.model_dump()
        elif isinstance(result, dict):
            result_dict = result
        else:
            result_dict = {}
        return SendCommandResponse(session_id=session_id, result=result_dict)

    @app.websocket("/sessions/{session_id}/ws")
    async def session_events_ws(
        session_id: str,
        websocket: WebSocket,
    ) -> None:
        """WebSocket 事件流。每个客户端独立 queue（WebSocketBridge.connect）。"""
        runtime = get_runtime_from_state(websocket.app.state)
        bridge = get_ws_bridge_from_state(websocket.app.state, runtime=runtime)
        await websocket.accept()
        try:
            async with bridge.connect(session_id) as conn:
                async for event in conn.events():
                    await websocket.send_text(json.dumps(event, default=str))
        except WebSocketDisconnect:
            logger.debug("ws disconnected: session_id=%s", session_id)


__all__ = [
    "CancelRequest",
    "CancelResponse",
    "SendCommandRequest",
    "SendCommandResponse",
    "SessionInfoResponse",
    "SessionListResponse",
    "StartSessionRequest",
    "create_app",
]
