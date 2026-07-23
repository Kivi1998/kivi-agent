"""FastAPI Gateway 骨架（Wave 1 / D 阶段 + Wave 3 WT-E1 联调升级）。

提供 6 个 HTTP / WebSocket 路由：
1. POST   /sessions                            — 创建并启动 session
2. GET    /sessions                            — 列出 user 的所有 session
3. GET    /sessions/{session_id}               — 查询单个 session
4. POST   /sessions/{session_id}/cancel        — 取消运行中的 session（v1 §5.2.2 SessionCancel）
5. POST   /sessions/{session_id}/commands      — 通用命令发送
6. WS     /sessions/{session_id}/ws            — 事件流（per-client queue）

Wave 3 WT-E1 升级（agent: package-web-gateway-v3）：
- 集成 GatewayEventBridge：core.bus 6 类业务事件 → WS 客户端
- 集成 HeartbeatEmitter：每 15s 推 ping 事件；前端 30s 没收到就断线提示
- 集成 EventReplayBuffer：缓存 100 条事件；重连时 `?since=<ts>` replay 漏掉事件
- cancel 推 RunCancelledEvent：POST /cancel 返回后立即推业务事件给所有 WS 客户端
- 错误码标准化：HTTPException / RequestValidationError 统一 `{detail, code, message, hint, ts}`

FastAPI / uvicorn / websockets 是 dev optional 依赖：
- 顶层 `gateway.__init__` 暴露 `create_app`，本模块 import 时不强制依赖
- 调用方在使用前需先 `uv sync --group dev`
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError as e:  # pragma: no cover - 由调用方处理
    raise ImportError(
        "kivi_agent.gateway 需要 fastapi 依赖。"
        "请先运行 `uv sync --group dev` 或 `uv pip install 'kivi-agent[gateway]'`。"
    ) from e

from kivi_agent.core.bus.commands import (
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.bus.events import RunCancelledEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.gateway.runtime import (
    AgentRuntime,
    SessionInfo,
)
from kivi_agent.gateway.deps import (
    get_runtime,
    get_runtime_from_state,
    get_ws_bridge_from_state,
)
from kivi_agent.gateway.event_bridge import GatewayEventBridge
from kivi_agent.gateway.heartbeat import HeartbeatEmitter
from kivi_agent.gateway.replay import EventReplayBuffer

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


# ---- 错误响应标准化（Wave 3 WT-E1）----

# 构造标准化错误响应（保留旧 detail 字段以兼容现有测试）
def _err_envelope(
    status_code: int, message: str, *, hint: str | None = None
) -> dict[str, Any]:
    """构造 `{detail, code, message, hint, ts}` 错误响应（agent: package-web-gateway-v3）。"""
    return {
        "detail": message,  # 兼容已有测试 `resp.json()["detail"]`
        "code": status_code,
        "message": message,
        "hint": hint,
        "ts": datetime.now(UTC).isoformat(),
    }


# HTTPException 转标准化错误响应
def _http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """HTTPException → 标准化错误 JSON（agent: package-web-gateway-v3）。"""
    assert isinstance(exc, HTTPException)  # narrow for mypy
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    hint: str | None = None
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        hint = "check session_id is correct or list sessions to find valid ids"
    elif exc.status_code == status.HTTP_400_BAD_REQUEST:
        hint = "verify request body fields match the documented schema"
    body = _err_envelope(exc.status_code, message, hint=hint)
    return JSONResponse(status_code=exc.status_code, content=body)


# 请求体 Pydantic 校验失败 → 标准化 422 响应
def _validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    """RequestValidationError → 标准化 422 错误 JSON（agent: package-web-gateway-v3）。"""
    assert isinstance(exc, RequestValidationError)  # narrow for mypy
    errors = exc.errors()
    # 简洁 message：第一个错误的字段路径 + msg
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", "validation error")
        message = f"{loc}: {msg}" if loc else msg
    else:
        message = "request validation error"
    body = _err_envelope(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        message,
        hint="check field types and required fields per OpenAPI schema",
    )
    # 保留原始 errors 列表（额外字段），便于客户端精确定位
    body["errors"] = [
        {
            "loc": list(e.get("loc", [])),
            "msg": e.get("msg", ""),
            "type": e.get("type", ""),
        }
        for e in errors
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body
    )


# ---- 应用工厂 ----

# kivi-core 守护进程地址（默认 127.0.0.1:7437，与 SocketServer 默认值一致）
DEFAULT_CORE_HOST = "127.0.0.1"
DEFAULT_CORE_PORT = 7437


# 构造 FastAPI lifespan：启动 event_bridge + heartbeat；停止时清理
def _build_lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """根据 app.state 已注入的依赖构造 lifespan 上下文管理器。"""

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        # 启动：实例化 bridge + heartbeat；replay_buffer 已在 create_app 阶段构造
        ws_bridge = _app.state.ws_bridge
        bus: EventBus | None = getattr(_app.state, "event_bus", None)
        if ws_bridge is not None and bus is not None:
            bridge = GatewayEventBridge(bus=bus, ws_bridge=ws_bridge)
            bridge.start()
            _app.state.event_bridge = bridge
            heartbeat = HeartbeatEmitter(bus=bus, interval_s=15.0)
            heartbeat.start()
            _app.state.heartbeat = heartbeat
            logger.debug("gateway lifespan: bridge + heartbeat started")
        try:
            yield
        finally:
            # 关闭：先停 heartbeat（不再发 ping），再停 bridge（不再 dispatch）
            heartbeat_obj: HeartbeatEmitter | None = getattr(
                _app.state, "heartbeat", None
            )
            if heartbeat_obj is not None:
                await heartbeat_obj.stop()
            bridge_obj: GatewayEventBridge | None = getattr(
                _app.state, "event_bridge", None
            )
            if bridge_obj is not None:
                bridge_obj.stop()
            logger.debug("gateway lifespan: bridge + heartbeat stopped")

    return _lifespan


# 提取 ws_bridge（已存在则直接返回；不存在时返回 None）
def _get_ws_bridge_or_none(state: Any) -> Any:
    """从 app.state 取 ws_bridge；不存在返回 None（agent: package-web-gateway-v3）。"""
    return getattr(state, "ws_bridge", None)


# 把 RunCancelledEvent 推给所有 WS 客户端（同时写入 replay 缓冲）
async def _dispatch_run_cancelled(
    request: Request, session_id: str, reason: str, ts: str
) -> None:
    """cancel 成功后推 RunCancelledEvent 给 WS 客户端（agent: package-web-gateway-v3）。"""
    state = request.app.state
    run_id: str | None = getattr(state, "session_to_run", {}).get(session_id)
    if not run_id:
        return  # 没有 run_id 无法构造事件（fake runtime 可能不返回 run_id）
    event = RunCancelledEvent(run_id=run_id, reason=reason, ts=ts)
    event_dict = event.model_dump(mode="json")
    event_dict["session_id"] = session_id
    bridge = _get_ws_bridge_or_none(state)
    if bridge is not None:
        try:
            await bridge.publish(event_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cancel dispatch failed: %s", exc)
    replay: EventReplayBuffer | None = getattr(state, "replay_buffer", None)
    if replay is not None:
        replay.push(session_id, event_dict)


# 创建 FastAPI 应用骨架
def create_app(
    runtime: AgentRuntime | None = None,
    *,
    core_host: str | None = None,
    core_port: int | None = None,
    event_bus: EventBus | None = None,
    enable_background_services: bool = True,
) -> FastAPI:
    """构造 FastAPI Gateway。

    参数：
    - `runtime`: 可选 AgentRuntime 实例（测试时注入 fake，生产由 lifespan 创建真实 Adapter）
    - `core_host` / `core_port`: 注入 kivi-core 守护进程地址（供 lifespan 创建 Adapter）
    - `event_bus`: 可选 EventBus（测试时注入 fake，生产由 lifespan 注入真实 bus）
    - `enable_background_services`: 是否启动 event_bridge / heartbeat 后台服务（默认 True）
    """
    _host = core_host or os.environ.get("KAMA_HOST", DEFAULT_CORE_HOST)
    _port = core_port if core_port is not None else int(
        os.environ.get("KAMA_PORT", str(DEFAULT_CORE_PORT))
    )
    _bus = event_bus if event_bus is not None else EventBus()

    # 先创建 app（不带 lifespan），把 state 注入后再挂 lifespan
    app = FastAPI(
        title="kivi-agent Gateway",
        version="0.0.1",
        description=(
            "Wave 1 / D 阶段骨架 + Wave 3 WT-E1 联调升级。"
            "FastAPI / uvicorn 是 dev optional 依赖。"
        ),
    )
    app.state.core_host = _host
    app.state.core_port = _port
    app.state.injected_runtime = runtime
    app.state.ws_bridge = None
    # Wave 3 WT-E1 新增 state：event_bus / event_bridge / heartbeat / replay_buffer / session_to_run
    app.state.event_bus = _bus
    app.state.event_bridge = None
    app.state.heartbeat = None
    app.state.replay_buffer = EventReplayBuffer()
    app.state.session_to_run = {}  # session_id -> run_id 映射（cancel 推 RunCancelledEvent 用）
    app.state.enable_background_services = enable_background_services

    # Wave 3 WT-E1 错误码标准化：注册两个 exception handler
    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)

    # Lifespan 必须先注册路由（lifespan 启动时可能用到 state 中的 ws_bridge 等）
    if enable_background_services:
        app.router.lifespan_context = _build_lifespan(app)

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
        # 记录 session_id → run_id 映射（cancel 推 RunCancelledEvent 用）
        if info.run_id:
            request.app.state.session_to_run[info.session_id] = info.run_id
        # 把 session_id 注册到 heartbeat（让该 session 收到 ping）
        heartbeat = getattr(request.app.state, "heartbeat", None)
        if heartbeat is not None:
            heartbeat.add_session(info.session_id)
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
        """取消运行中的 session（T5 接入 SessionCancelCommand + Wave 3 推 RunCancelledEvent）。"""
        from datetime import UTC, datetime  # noqa: F401  # 保持行内一致性

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
        # Wave 3 WT-E1：取消成功后推 RunCancelledEvent 给所有 WS 客户端
        if cancelled:
            await _dispatch_run_cancelled(request, session_id, req.reason, ts)
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

    # Wave 5.1 Eval Dashboard（agent: package-dashboard-api-v51）
    from kivi_agent.gateway.dashboard import build_dashboard_router

    app.include_router(build_dashboard_router())

    @app.websocket("/sessions/{session_id}/ws")
    async def session_events_ws(
        session_id: str,
        websocket: WebSocket,
    ) -> None:
        """WebSocket 事件流。每个客户端独立 queue（WebSocketBridge.connect）。

        Wave 3 WT-E1 升级：
        - 接受 `?since=<ts>` query：先 replay 漏掉事件，再 push 新事件
        - 连接时注册到 heartbeat，断开时反注册
        """
        runtime = get_runtime_from_state(websocket.app.state)
        bridge = get_ws_bridge_from_state(websocket.app.state, runtime=runtime)
        # 解析 ?since=<ts> query
        since_ts: str = websocket.query_params.get("since", "")
        await websocket.accept()
        # 路径遍历保护（虽然 query 不参与路径，但为防 ?since=../etc 透传）
        if ".." in since_ts:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        # 注册到 heartbeat
        heartbeat = getattr(websocket.app.state, "heartbeat", None)
        if heartbeat is not None:
            heartbeat.add_session(session_id)
        try:
            # Wave 3 WT-E1：先 replay 历史事件（从 EventReplayBuffer）
            replay: EventReplayBuffer | None = getattr(
                websocket.app.state, "replay_buffer", None
            )
            if replay is not None and since_ts:
                for ev in replay.since(session_id, since_ts):
                    await websocket.send_text(json.dumps(ev, default=str))
            async with bridge.connect(session_id) as conn:
                async for event in conn.events():
                    # Wave 3 WT-E1：实时事件也写入 replay 缓冲（保证后续重连能补齐）
                    if replay is not None and isinstance(event, dict):
                        replay.push(session_id, event)
                    await websocket.send_text(json.dumps(event, default=str))
        except WebSocketDisconnect:
            logger.debug("ws disconnected: session_id=%s", session_id)
        finally:
            if heartbeat is not None:
                heartbeat.remove_session(session_id)


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
