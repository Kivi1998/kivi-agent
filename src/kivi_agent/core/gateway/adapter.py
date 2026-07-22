"""RuntimeAdapter — 把现有 kivi-core IPC 桥接为 AgentRuntime。

设计原则（v1 契约 + D 报告 §迁移矩阵）：
- 这是**真**的 Adapter，不是 mock。所有方法走 `SocketClient` → kivi-core IPC
- 6 个方法对应 6 类用户操作：
  1. `start_session` → `session.create` + `session.send_message`
  2. `cancel_session` → `session.cancel`（A 阶段需补命令；当前 stub 走通用 method dispatch）
  3. `list_sessions` → `session.list`（A 阶段需补；当前返回空 list + 标记）
  4. `get_session` → `session.get_history` 间接验证存在
  5. `send_command` → 通用 method dispatch（按 `command.type` 作为 method）
  6. `subscribe_events` → `event.subscribe` + 从 `SocketClient` 事件流拉取
- 事件订阅返回 AsyncIterator，调用方用 `async for event in adapter.subscribe_events(...)`
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from kivi_agent.core.gateway.runtime import (
    Command,
    Event,
    Result,
    SessionInfo,
    SessionNotFoundError,
)
from kivi_agent.core.gateway.stub_protocol import (
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.transport.socket_client import IpcError, SocketClient


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


class RuntimeAdapter:
    """把 SocketClient 封装为 AgentRuntime。

    参数：
    - `client`: 已连接的 `SocketClient` 实例（调用方负责 connect / close）
    - `event_loop_task`: 客户端 `run_event_loop` 的 task，用于保持事件分发

    Adapter 假定 client 已经被 connect + 启动了 run_event_loop task。
    Adapter 不直接关闭 client（生命周期由 Gateway 管理）。
    """

    def __init__(self, client: SocketClient) -> None:
        self._client = client
        # 事件订阅的 session_id → 内部 subscription_id 映射
        self._sub_map: dict[str, str] = {}
        # 内部事件分发队列（按订阅的 session_id 分桶）
        self._queues: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        # 注册 SocketClient 的事件回调
        client.on_event(self._on_socket_event)

    # 客户端推送事件时：按 session_id 路由到对应队列
    async def _on_socket_event(self, event_data: dict[str, Any]) -> None:
        session_id = self._extract_session_id(event_data)
        if session_id is None:
            return
        queues = self._queues.get(session_id, [])
        for q in queues:
            await q.put(event_data)

    # 从事件 dict 中提取 session_id（D 报告：6 个新事件中有的带 session_id 字段）
    @staticmethod
    def _extract_session_id(event_data: dict[str, Any]) -> str | None:
        sid = event_data.get("session_id")
        if isinstance(sid, str):
            return sid
        # Run 事件没有 session_id；订阅 session 时不应收到 run-only 事件
        # 这里保守返回 None（让订阅者自行过滤）
        return None

    # 创建并启动新 session
    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        # 步骤 1：session.create（kivi-core 现有命令）
        create_params = {"mode": "chat", "title": goal[:40]}
        create_resp = await self._client.send_command("session.create", create_params)
        session_id = str(create_resp["session_id"])

        # 步骤 2：session.send_message 把 goal 投递给 Agent
        send_params = {"session_id": session_id, "content": goal}
        send_resp = await self._client.send_command("session.send_message", send_params)
        run_id = str(send_resp["run_id"])

        return SessionInfo(
            session_id=session_id,
            user_id=user_id,
            goal=goal,
            created_at=_now(),
            status="active",
            run_id=run_id,
        )

    # 取消运行中的 session
    async def cancel_session(self, session_id: str, reason: str) -> bool:
        # 构造 SessionCancelCommand 并走通用 method dispatch
        cmd = SessionCancelCommand(session_id=session_id, reason=reason)
        try:
            resp: BaseModel = await self.send_command(session_id, cmd)
        except IpcError as e:
            # kivi-core 尚未实装 session.cancel（A 阶段契约已冻结但命令未上 main）
            # 临时返回 False，标注 reason；A 阶段后会自动成功
            if e.code == -32601:  # METHOD_NOT_FOUND
                return False
            raise
        # 解析 SessionCancelResult
        if isinstance(resp, BaseModel):
            cancelled = getattr(resp, "cancelled", None)
            if isinstance(cancelled, bool):
                return cancelled
        return False

    # 列出 user_id 的所有 session
    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        # kivi-core 当前没有 session.list 命令（A 阶段待补）
        # 当前 best-effort：发一个 session.list RPC，如未实现则返回空
        try:
            resp = await self._client.send_command(
                "session.list", {"user_id": user_id}
            )
        except IpcError as e:
            if e.code == -32601:  # METHOD_NOT_FOUND
                return []
            raise
        items = resp.get("sessions", []) if isinstance(resp, dict) else []
        return [
            SessionInfo(
                session_id=str(item.get("session_id", "")),
                user_id=user_id,
                goal=str(item.get("title", "")),
                created_at=str(item.get("created_at", _now())),
                status=str(item.get("status", "active")),
                run_id=item.get("last_run_id"),
            )
            for item in items
        ]

    # 查询单个 session 元数据
    async def get_session(self, session_id: str) -> SessionInfo | None:
        # 用 session.get_history 间接确认 session 存在
        try:
            await self._client.send_command(
                "session.get_history", {"session_id": session_id}
            )
        except IpcError as e:
            if e.code in (-32601, -32010):  # METHOD_NOT_FOUND or SESSION_NOT_FOUND
                return None
            raise
        return SessionInfo(
            session_id=session_id,
            user_id="",  # kivi 当前不返回 user_id
            goal="",
            created_at="",
            status="active",
            run_id=None,
        )

    # 通用命令发送：按 command.type 决定 method，把 params 整体发出去
    async def send_command(self, session_id: str, command: Command) -> Result:
        if not isinstance(command, BaseModel):
            raise TypeError(f"command must be a pydantic BaseModel, got {type(command)}")

        cmd_dict = command.model_dump()
        # 把 session_id 注入 params（如果还没有）
        if "session_id" not in cmd_dict and session_id:
            cmd_dict["session_id"] = session_id
        method = cmd_dict.get("type")
        if not isinstance(method, str):
            raise ValueError(f"command.type must be a string, got {method!r}")

        # 通用 method dispatch：method 通常等于 command.type
        method_name = method
        resp_dict = await self._client.send_command(method_name, cmd_dict)

        # 尝试把响应按 command.type 反序列化为 Result 对应类
        result = self._coerce_result(command, resp_dict)
        return result  # type: ignore[return-value]

    # 把 socket 响应 dict 还原为 Result 类型（按 command.type 对应 Result）
    @staticmethod
    def _coerce_result(command: BaseModel, resp: dict[str, Any]) -> BaseModel:
        # 当前阶段：A 阶段命令 Result 类尚未全部进入 main；只对已知的 SessionCancel 做强转
        if isinstance(command, SessionCancelCommand):
            return SessionCancelResult.model_validate(resp)
        # 通用：返回一个 dummy BaseModel 容纳字段，避免 strict 类型失败
        # 上层 (FastAPI route) 会 dict 化后返回
        return _DictResult(data=resp)

    # 订阅 session 的事件流
    async def subscribe_events(self, session_id: str) -> AsyncIterator[Event]:
        # 每次订阅独立 queue（D 报告 §迁移矩阵第 12 项关键：禁止共用单一队列）
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.setdefault(session_id, []).append(queue)
        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        self._sub_map[session_id] = sub_id

        try:
            # 向 core 发送 event.subscribe
            await self._client.send_command(
                "event.subscribe",
                {
                    "topics": ["*"],
                    "scope": f"session:{session_id}",
                },
            )
        except IpcError:
            # 订阅失败仍然要清理 queue
            self._dequeue(session_id, queue)
            raise

        try:
            while True:
                event_data = await queue.get()
                yield event_data  # type: ignore[misc]
        finally:
            self._dequeue(session_id, queue)

    # 清理订阅者 queue
    def _dequeue(
        self, session_id: str, queue: asyncio.Queue[dict[str, Any]]
    ) -> None:
        queues = self._queues.get(session_id)
        if queues is None:
            return
        try:
            queues.remove(queue)
        except ValueError:
            pass
        if not queues:
            self._queues.pop(session_id, None)
            self._sub_map.pop(session_id, None)


class _DictResult(BaseModel):
    """通用 Result fallback：把响应 dict 整体打包。"""

    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
