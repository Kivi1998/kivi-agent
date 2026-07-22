"""EventBus 的 Fake 实现。

设计要点：
- 兼容 `kivi_agent.core.events.bus.EventBus` 的全部接口
- 额外提供 `events` 列表（已发布事件的全量快照）和 `published_types` 计数器
- 支持 handler 抛异常的"故障注入"模式（off / log / raise）
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)


class FaultMode(str, Enum):
    """handler 异常的故障注入模式。"""

    OFF = "off"  # 正常
    LOG = "log"  # 记录但不抛
    RAISE = "raise"  # 抛出（用于测试容错）


# EventHandler 类型同生产 EventBus
EventHandler = Callable[[BaseModel], Awaitable[None]]


class FakeEventBus:
    """EventBus 替身，支持事件快照 + 故障注入。

    与生产 EventBus 的差异：
    - 增加 `events` 全量记录
    - 增加 `published_types` 计数
    - 增加 `fault_mode` 控制 handler 异常行为
    """

    def __init__(self, fault_mode: FaultMode = FaultMode.OFF) -> None:
        self._subscribers: list[EventHandler] = []
        self._fault_mode = fault_mode
        # 观测字段
        self.events: list[BaseModel] = []
        self.published_types: Counter[str] = Counter()
        self.handler_errors: list[BaseException] = []

    # 订阅事件处理函数
    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    # 取当前订阅者数量
    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # 按注册顺序调用所有订阅者
    async def publish(self, event: BaseModel) -> None:
        self.events.append(event)
        # 用 type 字段做 discriminator；pydantic 模型都有 .type
        event_type = getattr(event, "type", event.__class__.__name__)
        self.published_types[event_type] += 1

        for handler in self._subscribers:
            try:
                await handler(event)
            except Exception as exc:  # noqa: BLE001
                self.handler_errors.append(exc)
                if self._fault_mode == FaultMode.RAISE:
                    raise
                if self._fault_mode == FaultMode.LOG:
                    log.warning("FakeEventBus handler raised: %s", exc)

    # 断言辅助：检查某类型事件是否被发布
    def assert_published(self, event_type: str, *, count: int | None = None) -> None:
        actual = self.published_types.get(event_type, 0)
        if count is None:
            assert actual >= 1, f"事件 {event_type} 未被发布（实际 {actual} 次）"
        else:
            assert actual == count, f"事件 {event_type} 期望 {count} 次，实际 {actual} 次"

    # 重置观测状态（保留订阅者）
    def reset(self) -> None:
        self.events = []
        self.published_types = Counter()
        self.handler_errors = []
