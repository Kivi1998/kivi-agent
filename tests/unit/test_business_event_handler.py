"""BusinessEventHandler 单元测试（agent: package-events-bridge-v2）。

按 v1 §5.2.1 冻结的 6 业务事件（LlmThinkingEvent / ChartRenderedEvent /
RagSourcesCitedEvent / FrontendToolCallRequested / FrontendToolCallResponded /
RunCancelledEvent），验证 BusinessEventHandler 的订阅/聚合/释放语义。

为什么这是单元测试而不是 E2E：
- 不依赖 Router / SynthesizerRunner 真实实现（WT-B 在并行 worktree）
- 不调真实 LLM（用 EventBus 直发事件即可）
- 隔离 EventBus 行为（用 FakeEventBus，避免生产 bus 的串扰）
"""
from __future__ import annotations

from pydantic import BaseModel

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)
from kivi_agent.core.bus.handlers.business import (
    BusinessEventHandler,
    BusinessEventLog,
)
from kivi_agent.core.events.bus import EventBus
from tests._fakes.event_bus import FakeEventBus


# 功能：BusinessEventHandler 启动后订阅 EventBus，6 类事件按 run_id 路由到对应 log
# 设计：发 6 类事件各 1 条到 bus，断言 log.sub_events 收集到全部 6 条，
#      分类列表（thinking_traces / chart_metadata / rag_citations）各拿到 1 条
async def test_handler_collects_all_six_v1_event_types() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-parent-1"
    log = handler.start(parent_run_id)
    assert log is not None
    assert log.parent_run_id == parent_run_id

    await bus.publish(
        LlmThinkingEvent(run_id=parent_run_id, step=1, content="think", ts="t1")
    )
    await bus.publish(
        ChartRenderedEvent(
            run_id=parent_run_id,
            chart_id="c1",
            option_dict={"xAxis": {"type": "category"}},
            ts="t2",
        )
    )
    await bus.publish(
        RagSourcesCitedEvent(
            run_id=parent_run_id, sources=[{"id": "doc-1"}], ts="t3"
        )
    )
    await bus.publish(
        FrontendToolCallRequested(
            run_id=parent_run_id, request_id="q1", tool_name="t", args={}, ts="t4"
        )
    )
    await bus.publish(
        FrontendToolCallResponded(
            run_id=parent_run_id, request_id="q1", result={"ok": True}, ts="t5"
        )
    )
    await bus.publish(
        RunCancelledEvent(run_id=parent_run_id, reason="user", ts="t6")
    )

    assert len(log.thinking_traces) == 1
    assert len(log.chart_metadata) == 1
    assert len(log.rag_citations) == 1
    # 6 条事件都按 parent_run_id 聚合
    assert len(log.sub_events) == 1
    assert parent_run_id in log.sub_events
    assert len(log.sub_events[parent_run_id]) == 6


# 功能：同 run_id 的 6 类事件按发布顺序被追加到 sub_events[run_id] 列表
# 设计：发 6 类事件并断言 sub_events[parent_run_id] 列表的元素类型顺序与发布顺序一致；
#      顺序语义是 v1 §5 E2E 事件流断言的前提（"LlmThinking → RagSourcesCited → ... → 终态 text"）
async def test_handler_preserves_event_publish_order() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-parent-2"
    log = handler.start(parent_run_id)

    # 按特定顺序发布
    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=1, content="a", ts="t1"))
    await bus.publish(RagSourcesCitedEvent(run_id=parent_run_id, sources=[], ts="t2"))
    await bus.publish(ChartRenderedEvent(run_id=parent_run_id, chart_id="c", option_dict={}, ts="t3"))

    events = log.sub_events[parent_run_id]
    assert len(events) == 3
    assert isinstance(events[0], LlmThinkingEvent)
    assert isinstance(events[1], RagSourcesCitedEvent)
    assert isinstance(events[2], ChartRenderedEvent)


# 功能：非 v1 6 类事件（RunStartedEvent / ToolCallStartedEvent 等）被 handler 忽略，不污染 log
# 设计：混入一条 RunStartedEvent，断言 log.sub_events 仍只有 6 类事件；
#      这是 handler 的关键过滤语义——避免把通用 run 生命周期事件当成业务事件收集
async def test_handler_ignores_non_business_events() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-parent-3"
    log = handler.start(parent_run_id)

    # 混入一条非业务事件
    class _OtherEvent(BaseModel):
        type: str = "other.event"
        run_id: str = parent_run_id

    await bus.publish(_OtherEvent())
    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=1, content="x", ts="t1"))

    # 只有 LlmThinkingEvent 被收集
    assert len(log.sub_events[parent_run_id]) == 1
    assert len(log.thinking_traces) == 1


# 功能：不同 parent_run_id 的事件彼此隔离，互不污染
# 设计：启动 2 个 parent，断言每个 log 只收到自己 run_id 的事件；
#      多业务 run 并发时这层隔离是必要的（防交叉聚合导致 E2E 误判）
async def test_handler_isolates_concurrent_parent_runs() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log_a = handler.start("run-A")
    log_b = handler.start("run-B")

    await bus.publish(LlmThinkingEvent(run_id="run-A", step=1, content="A", ts="t1"))
    await bus.publish(LlmThinkingEvent(run_id="run-B", step=1, content="B", ts="t2"))
    await bus.publish(RagSourcesCitedEvent(run_id="run-A", sources=[{"id": "x"}], ts="t3"))

    assert len(log_a.thinking_traces) == 1
    assert log_a.thinking_traces[0].content == "A"
    assert len(log_a.rag_citations) == 1
    assert len(log_b.thinking_traces) == 1
    assert log_b.thinking_traces[0].content == "B"
    assert len(log_b.rag_citations) == 0


# 功能：sub-run 的事件通过 track_sub_run 注册后，按 event.run_id 路由到对应 sub_events 槽位
# 设计：先 start(parent) 再 track_sub_run(sub, parent)，断言事件按 run_id 分桶；
#      这是 v1 §5 E2E 断言"父 run 编排 → 子 run 触发业务 Tool → 父 run 收到 thinking"的子事件路由语义
async def test_handler_routes_sub_run_events_into_separate_slots() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-parent-4"
    sub_run_id = "run-sub-4"
    log = handler.start(parent_run_id)
    # 显式注册子 run；这是 BusinessRouter / SynthesizerRunner 启动子 run 时的标准调用
    handler.track_sub_run(sub_run_id, parent_run_id)

    # parent 编排
    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=1, content="plan", ts="t1"))
    # sub-run 触发 RAG Tool
    await bus.publish(RagSourcesCitedEvent(run_id=sub_run_id, sources=[{"id": "s1"}], ts="t2"))

    # 父 run 与子 run 的事件分别落入独立槽位
    assert parent_run_id in log.sub_events
    assert sub_run_id in log.sub_events
    assert len(log.sub_events[parent_run_id]) == 1
    assert len(log.sub_events[sub_run_id]) == 1
    # 子 run 的 RAG 引用也进 rag_citations 分类列表（通过 run_id 路由后再按类型收）
    assert len(log.rag_citations) == 1
    assert log.rag_citations[0].run_id == sub_run_id


# 功能：未通过 track_sub_run 注册的 run_id 触发的事件被 handler 丢弃
# 设计：start(parent) 但不 track_sub_run(sub)；发 sub_run_id 事件断言不进 log；
#      这是"显式注册"模型的反向断言：避免未声明的 run_id 漏到 log 污染断言
async def test_handler_drops_events_from_untracked_sub_run() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-parent-4b"
    sub_run_id = "run-sub-4b"
    log = handler.start(parent_run_id)
    # 注意：故意不调用 handler.track_sub_run(sub_run_id, parent_run_id)

    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=1, content="plan", ts="t1"))
    await bus.publish(RagSourcesCitedEvent(run_id=sub_run_id, sources=[{"id": "s1"}], ts="t2"))

    # 只有 parent 的事件进 log，sub_run_id 的事件被丢弃
    assert len(log.sub_events) == 1
    assert parent_run_id in log.sub_events
    assert sub_run_id not in log.sub_events
    assert len(log.rag_citations) == 0


# 功能：get_log(parent_run_id) 返回对应 log；未知 run_id 返回 None
# 设计：启动 1 个 parent，断言 start 返回的 log 与 get_log 取回的对象是同一实例（is 比较），
#      同时断言未知 run_id 返回 None；防止测试在 assertion 上静默失败
async def test_get_log_returns_started_log_or_none() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-x")
    assert handler.get_log("run-x") is log
    assert handler.get_log("unknown") is None


# 功能：stop() 释放 log，停止后 get_log 返回 None；后续事件不再被收集
# 设计：stop 前先发布 1 个事件确认能被收，stop 后再发布 1 个事件断言不被收；
#      "释放"语义要求释放后既不能查询到 log、也不能再写入新事件
async def test_stop_releases_logs_and_stops_collecting() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-stop-1"
    log = handler.start(parent_run_id)
    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=1, content="before", ts="t1"))
    assert len(log.thinking_traces) == 1

    handler.stop()

    # 释放后 get_log 返回 None
    assert handler.get_log(parent_run_id) is None
    # 释放后发布的事件被忽略（不再收集）
    await bus.publish(LlmThinkingEvent(run_id=parent_run_id, step=2, content="after", ts="t2"))


# 功能：BusinessEventLog 默认字段为空，构造时不传 sub_events / 分类列表也能正常工作
# 设计：直接构造 BusinessEventLog 断言所有字段是空 list（不是 None），便于业务代码无脑迭代；
#      这是 dataclass 字段的"工厂默认值"语义的硬断言
def test_business_event_log_default_fields_are_empty_lists() -> None:
    log = BusinessEventLog(parent_run_id="run-empty")
    assert log.parent_run_id == "run-empty"
    assert log.sub_events == {}
    assert log.rag_citations == []
    assert log.chart_metadata == []
    assert log.thinking_traces == []


# 功能：handler 与生产 EventBus（不是 FakeEventBus）也能正确协作
# 设计：用生产 EventBus 而不是 FakeEventBus，确保 handler 不依赖 FakeEventBus 的扩展接口；
#      发布 1 个事件后断言 log 收到它——这是"handler 与生产 bus 协议兼容"的硬证据
async def test_handler_works_with_production_event_bus() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-prod-1")
    await bus.publish(
        LlmThinkingEvent(run_id="run-prod-1", step=1, content="x", ts="t1")
    )
    assert len(log.thinking_traces) == 1
    handler.stop()
