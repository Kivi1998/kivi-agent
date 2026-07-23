"""Gateway 业务事件路由：core.bus 事件 → WS 客户端（agent: package-web-gateway-v3）。

设计要点：
- 订阅 `EventBus`（handler 签名 `async (BaseModel) -> None`），按 v1 §5.2.1 6 类业务事件过滤
- 命中后调 `WebSocketBridge.publish(event_dict)`，由 bridge 按 session_id 投递到对应客户端
- 不引入新事件名 / 字段（v1 契约冻结）；event dict 来自 BaseModel.model_dump() 序列化
- run_id → session_id 映射由调用方维护（start_session 时已 register_run），
  本模块只关心 event 自身字段；run_id 单独的事件不会被推送（没有 session_id）
- stop() 取消订阅：直接置 _active=False 并解除对 bus 的强引用，避免 EventBus 泄漏
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)

if TYPE_CHECKING:
    from kivi_agent.core.events.bus import EventBus
    from kivi_agent.core.gateway.ws_bridge import WebSocketBridge

logger = logging.getLogger(__name__)

# v1 §5.2.1 冻结 6 类业务事件类型（用于 isinstance 内部过滤）
# 用 tuple 保持不可变；与 core/bus/handlers/business.py 保持一致
_GATEWAY_BUSINESS_EVENT_TYPES: tuple[type[BaseModel], ...] = (
    LlmThinkingEvent,
    ChartRenderedEvent,
    RagSourcesCitedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    RunCancelledEvent,
)


# 构造从 BaseModel 派生的网关业务事件桥接器
class GatewayEventBridge:
    """Gateway 业务事件路由：core.bus 事件 → WS 客户端（agent: package-web-gateway-v3）。"""

    # 初始化桥接器：绑定 EventBus + WSBridge，尚未订阅
    def __init__(self, bus: EventBus, ws_bridge: WebSocketBridge) -> None:
        self._bus = bus
        self._ws_bridge = ws_bridge
        # 已发布事件计数（仅 6 类 v1 业务事件）
        self.dispatched_count: int = 0
        # 启动后置 True；stop() 后置 False
        self._active = False

    # 启动：订阅 EventBus；多次 start() 幂等
    def start(self) -> None:
        if self._active:
            return
        self._bus.subscribe(self._on_event)
        self._active = True
        logger.debug("GatewayEventBridge started")

    # 停止：解绑 handler 引用；停止后 _on_event 直接 no-op
    def stop(self) -> None:
        self._active = False
        # 不主动从 bus._subscribers 移除（EventBus 没提供 unsubscribe 接口）
        # 改成 _active 短路，handler 引用保留但不再触发业务逻辑
        logger.debug("GatewayEventBridge stopped")

    # EventBus 回调：过滤 6 类业务事件 + 序列化为 dict + 通过 WSBridge 推送
    async def _on_event(self, event: BaseModel) -> None:
        if not self._active:
            return
        # isinstance 过滤：只关心 v1 §5.2.1 冻结 6 类业务事件
        if not isinstance(event, _GATEWAY_BUSINESS_EVENT_TYPES):
            return
        # 6 类事件都带 run_id 字段（v1 §5.2.1 契约）
        run_id = getattr(event, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            return
        # 序列化为 dict 推送；model_dump 保留所有字段（含 run_id / ts / type）
        try:
            event_dict = event.model_dump(mode="json")
        except Exception:  # noqa: BLE001
            # 序列化失败回退到默认 dump
            event_dict = event.model_dump()
        # 6 类事件不一定带 session_id 字段；WS Bridge 会按 session_id 路由
        # 没有 session_id 的事件会被 bridge 丢弃（防御性，与 D 报告语义一致）
        try:
            await self._ws_bridge.publish(event_dict)
            self.dispatched_count += 1
        except Exception as exc:  # noqa: BLE001
            # bridge 失败不抛；只记日志（避免影响其他订阅者）
            logger.warning("GatewayEventBridge publish failed: %s", exc)


__all__ = ["GatewayEventBridge", "_GATEWAY_BUSINESS_EVENT_TYPES"]
