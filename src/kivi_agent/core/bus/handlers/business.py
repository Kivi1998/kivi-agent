"""业务 Agent 事件 handler（agent: package-events-bridge-v2）。

按 v1 §5.2.1 冻结的 6 类业务事件（LlmThinkingEvent / ChartRenderedEvent /
RagSourcesCitedEvent / FrontendToolCallRequested / FrontendToolCallResponded /
RunCancelledEvent），订阅 EventBus 并按 run_id 维度聚合到 BusinessEventLog。

路由模型：
- 每个 log 关联一组 tracked run_id（init: {parent_run_id}）
- 上游 BusinessRouter / SynthesizerRunner 启动子 run 时调用
  ``handler.track_sub_run(sub_run_id, parent_run_id)`` 注册
- EventBus 推送事件时按 ``event.run_id`` 查表；命中则落入对应 log
- 未注册的 run_id 直接丢弃（避免多 log 交叉污染）

与 v1 既有 EventBus 协议的协调：
- 生产 EventBus.subscribe(handler) 只接受单一 handler 回调（无 type 过滤参数）
- 本 handler 通过 isinstance 内部过滤；不引入 type-based dispatch 以避免
  触碰 core/events/bus.py（属于核心事件基础设施，扩展须经 ADR）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)
from kivi_agent.core.events.bus import EventBus

# v1 §5.2.1 冻结的 6 类业务事件类型（用于 isinstance 内部过滤）
# 内部常量；类型注解用 tuple 而非 set 保持不可变
_BUSINESS_EVENT_TYPES: tuple[type[BaseModel], ...] = (
    LlmThinkingEvent,
    ChartRenderedEvent,
    RagSourcesCitedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    RunCancelledEvent,
)


# 业务事件日志：按 run_id 维度收集事件（agent: package-events-bridge-v2）
@dataclass
class BusinessEventLog:
    """业务事件日志：收集 v1 §5.2.1 6 类业务事件，按 run_id 分桶。

    parent_run_id 是触发整个业务编排的 run（多意图 query 入口）；
    sub_events 字典的 key 既可以是 parent_run_id（父 run 自己触发的事件），
    也可以是 sub_run_id（子 run 触发的事件）。
    """

    parent_run_id: str
    sub_events: dict[str, list[BaseModel]] = field(default_factory=dict)
    rag_citations: list[RagSourcesCitedEvent] = field(default_factory=list)
    chart_metadata: list[ChartRenderedEvent] = field(default_factory=list)
    thinking_traces: list[LlmThinkingEvent] = field(default_factory=list)


# 业务 Agent 事件 handler（agent: package-events-bridge-v2）
class BusinessEventHandler:
    """订阅 EventBus，把 6 类业务事件按 run_id 路由到对应 BusinessEventLog。

    用法：
        bus = EventBus()
        handler = BusinessEventHandler(bus)
        log = handler.start("run-parent-1")
        handler.track_sub_run("run-sub-1", "run-parent-1")  # 启动子 run 时注册
        ... # 上游业务 Agent 在 bus 上发布事件
        log.thinking_traces  # 收集到的 LlmThinkingEvent
        handler.stop()       # 释放 log
    """

    # 初始化 handler 并订阅 EventBus
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        # run_id -> BusinessEventLog：每个 tracked run_id 落到一个 log
        self._log_for_run: dict[str, BusinessEventLog] = {}
        # parent_run_id -> BusinessEventLog：方便 get_log(parent_run_id) O(1) 查
        self._logs: dict[str, BusinessEventLog] = {}
        # stop() 后置 False，事件直接 no-op（避免反复分配又删除 log）
        self._active = True
        bus.subscribe(self._on_event)

    # 启动一个 parent run 的事件收集，返回对应的 BusinessEventLog
    def start(self, parent_run_id: str) -> BusinessEventLog:
        log = BusinessEventLog(parent_run_id=parent_run_id)
        self._logs[parent_run_id] = log
        self._log_for_run[parent_run_id] = log
        return log

    # 注册子 run 到 parent run；子 run 触发的事件按 sub_run_id 路由到 parent log
    def track_sub_run(self, sub_run_id: str, parent_run_id: str) -> None:
        log = self._logs.get(parent_run_id)
        if log is None:
            return  # parent 未启动；忽略静默（业务约定：先 start 再 track）
        self._log_for_run[sub_run_id] = log

    # 停止 handler：释放所有 log；后续事件不再被收集
    def stop(self) -> None:
        self._logs.clear()
        self._log_for_run.clear()
        self._active = False

    # 取已启动的 parent run 对应的 log；未知 run_id 返回 None
    def get_log(self, parent_run_id: str) -> BusinessEventLog | None:
        return self._logs.get(parent_run_id)

    # EventBus 回调：按类型过滤 + 按 run_id 路由到对应 log
    async def _on_event(self, event: BaseModel) -> None:
        if not self._active:
            return
        # isinstance 过滤：只关心 v1 §5.2.1 6 类业务事件
        if not isinstance(event, _BUSINESS_EVENT_TYPES):
            return
        # run_id 是所有 6 类事件的共有字段（v1 §5.2.1 契约）
        run_id = getattr(event, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            return
        # 路由：按 run_id 查 log；未注册的 run_id 直接忽略
        log = self._log_for_run.get(run_id)
        if log is None:
            return
        # sub_events 槽位按 run_id 追加
        bucket = log.sub_events.setdefault(run_id, [])
        bucket.append(event)
        # 分类列表按类型追加（已通过 run_id 查表，按类型二次过滤）
        if isinstance(event, LlmThinkingEvent):
            log.thinking_traces.append(event)
        elif isinstance(event, ChartRenderedEvent):
            log.chart_metadata.append(event)
        elif isinstance(event, RagSourcesCitedEvent):
            log.rag_citations.append(event)
        # FrontendToolCallRequested / Responded / RunCancelledEvent
        # 暂不分类（业务场景未到），但已落入 sub_events 保留全量


__all__ = ["BusinessEventHandler", "BusinessEventLog"]
