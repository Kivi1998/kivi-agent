"""Gateway 心跳发射器：定期推 ping 事件到所有 WS 客户端（agent: package-web-gateway-v3）。

设计要点：
- 用 `EventBus.publish` 间接发送心跳：bus.publish → EventBridge._on_event → WSBridge.publish
  走与 6 类业务事件完全相同的推送通道，零特殊路径
- ping 事件格式：`{type: "ping", ts: <ISO 8601>, session_id: <session_id>}`
  加 session_id 是为了让 WSBridge 路由到正确客户端（bridge 按 session_id 投递）
- interval_s 默认 15s；前端 30s 没收到就断线提示（v1 §5.2.1 / Web Chat 计划 §三 WT-E1）
- start() 创建后台 task；stop() cancel 该 task
- 时间源可注入（便于测试）：测试时通过 monkeypatch asyncio.sleep 控制节奏
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from kivi_agent.core.events.bus import EventBus


logger = logging.getLogger(__name__)


# 内部 ping 事件：仅做 publish 用途，不进入 v1 契约
class _PingEvent(BaseModel):
    """心跳事件：仅 Gateway 内部使用，不属于 v1 §5.2.1 契约。"""

    type: str = "ping"
    ts: str
    session_id: str | None = None  # None 表示广播


# 构造定期推送 ping 事件到 EventBus 的发射器
class HeartbeatEmitter:
    """每 N 秒发 ping 事件（agent: package-web-gateway-v3）。"""

    # 初始化发射器：绑定 EventBus + 配置间隔
    def __init__(self, bus: EventBus, interval_s: float = 15.0) -> None:
        self._bus = bus
        self._interval_s = interval_s
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        # 已发 ping 计数
        self.ping_count: int = 0
        # 活跃 session 列表（用于 broadcast 模式）；start() 时为空 set
        self._active_sessions: set[str] = set()

    # 注册一个 session_id：心跳会带 session_id 让 WSBridge 路由到该客户端
    def add_session(self, session_id: str) -> None:
        if session_id:
            self._active_sessions.add(session_id)

    # 反注册一个 session_id：客户端断开后清理
    def remove_session(self, session_id: str) -> None:
        self._active_sessions.discard(session_id)

    # 当前活跃 session 数
    def active_session_count(self) -> int:
        return len(self._active_sessions)

    # 启动后台 task：周期性 publish ping 事件
    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopped.clear()
        self._task = asyncio.create_task(self._run(), name="gateway-heartbeat")

    # 停止后台 task：cancel + 等待 cleanup
    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    # 后台 loop：每 interval_s 发一次 ping（无活跃 session 时不发）
    async def _run(self) -> None:
        try:
            while not self._stopped.is_set():
                # 等待下一次 tick 或 stop 信号
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(), timeout=self._interval_s
                    )
                    return  # stop 信号到达
                except TimeoutError:
                    pass  # tick 到达
                # 给每个活跃 session 各发 1 条 ping
                sessions = list(self._active_sessions)
                if not sessions:
                    continue
                ts = datetime.now(UTC).isoformat()
                for sid in sessions:
                    try:
                        await self._bus.publish(_PingEvent(ts=ts, session_id=sid))
                        self.ping_count += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "HeartbeatEmitter publish failed for %s: %s", sid, exc
                        )
        except asyncio.CancelledError:
            pass


__all__ = ["HeartbeatEmitter", "_PingEvent"]
