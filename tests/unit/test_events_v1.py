from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    Event,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)


# 功能：LlmThinkingEvent 序列化往返后字段完整保留
# 设计：构造完整 4 字段实例，JSON 往返后断言 4 字段值；
#      这是 v1 §5.2.1 推理内容事件的字段契约
def test_llm_thinking_event_roundtrip() -> None:
    evt = LlmThinkingEvent(
        run_id="r-1", step=1, content="reasoning...", ts="2026-01-01T00:00:00Z"
    )
    data = evt.model_dump()
    assert data["type"] == "llm.thinking"
    restored = LlmThinkingEvent.model_validate(data)
    assert restored.run_id == "r-1"
    assert restored.step == 1
    assert restored.content == "reasoning..."
    assert restored.ts == "2026-01-01T00:00:00Z"


# 功能：ChartRenderedEvent 序列化往返后字段完整保留（含 option_dict）
# 设计：构造带 echarts option 的实例，JSON 往返后断言嵌套字段值；
#      这是 v1 §5.2.1 图表元数据事件的字段契约
def test_chart_rendered_event_roundtrip() -> None:
    evt = ChartRenderedEvent(
        run_id="r-1",
        chart_id="c-1",
        option_dict={"xAxis": {"type": "category"}, "series": [{"type": "bar"}]},
        ts="2026-01-01T00:00:00Z",
    )
    data = evt.model_dump()
    assert data["type"] == "chart.rendered"
    restored = ChartRenderedEvent.model_validate(data)
    assert restored.chart_id == "c-1"
    assert restored.option_dict["xAxis"]["type"] == "category"


# 功能：RagSourcesCitedEvent 序列化往返后 sources list 完整保留
# 设计：构造带 2 个 source dict 的实例，断言 list 长度与字段值；
#      这是 v1 §5.2.1 RAG 引用溯源事件的字段契约
def test_rag_sources_cited_event_roundtrip() -> None:
    evt = RagSourcesCitedEvent(
        run_id="r-1",
        sources=[{"id": "doc-1", "title": "x"}, {"id": "doc-2", "title": "y"}],
        ts="2026-01-01T00:00:00Z",
    )
    data = evt.model_dump()
    assert data["type"] == "rag.sources_cited"
    restored = RagSourcesCitedEvent.model_validate(data)
    assert len(restored.sources) == 2
    assert restored.sources[0]["id"] == "doc-1"


# 功能：FrontendToolCallRequested 序列化往返后字段完整保留
# 设计：构造带 request_id / tool_name / args 的实例；
#      这是 v1 §5.2.1 前端工具调用请求事件的字段契约（D 阶段 Web 接收 + request_id 关联）
def test_frontend_tool_call_requested_roundtrip() -> None:
    evt = FrontendToolCallRequested(
        run_id="r-1",
        request_id="req-1",
        tool_name="open_url",
        args={"url": "https://example.com"},
        ts="2026-01-01T00:00:00Z",
    )
    data = evt.model_dump()
    assert data["type"] == "frontend.tool_call_requested"
    restored = FrontendToolCallRequested.model_validate(data)
    assert restored.request_id == "req-1"
    assert restored.tool_name == "open_url"
    assert restored.args["url"] == "https://example.com"


# 功能：FrontendToolCallResponded 序列化往返后字段完整保留
# 设计：构造带 request_id / result 的实例，断言 result 字段值；
#      这是 v1 §5.2.1 前端工具调用响应事件的字段契约
def test_frontend_tool_call_responded_roundtrip() -> None:
    evt = FrontendToolCallResponded(
        run_id="r-1",
        request_id="req-1",
        result={"ok": True, "data": [1, 2, 3]},
        ts="2026-01-01T00:00:00Z",
    )
    data = evt.model_dump()
    assert data["type"] == "frontend.tool_call_responded"
    restored = FrontendToolCallResponded.model_validate(data)
    assert restored.request_id == "req-1"
    assert restored.result["ok"] is True


# 功能：RunCancelledEvent 序列化往返后字段完整保留
# 设计：构造带 reason 的实例，断言 reason 字段值；
#      这是 v1 §5.2.1 Run 取消事件的字段契约（任意入口都能取消）
def test_run_cancelled_event_roundtrip() -> None:
    evt = RunCancelledEvent(
        run_id="r-1",
        reason="user_requested",
        ts="2026-01-01T00:00:00Z",
    )
    data = evt.model_dump()
    assert data["type"] == "run.cancelled"
    restored = RunCancelledEvent.model_validate(data)
    assert restored.run_id == "r-1"
    assert restored.reason == "user_requested"


# 功能：6 个新事件能通过 Event 判别联合正确反序列化
# 设计：用 TypeAdapter(Event) 把每个事件的 JSON 反序列化回 union，
#      断言 round-trip 后 type 仍为原类型；这是 IPC 协议路由的基础
@pytest.mark.parametrize(
    "evt",
    [
        LlmThinkingEvent(
            run_id="r", step=1, content="x", ts="2026-01-01T00:00:00Z"
        ),
        ChartRenderedEvent(
            run_id="r", chart_id="c", option_dict={"a": 1}, ts="2026-01-01T00:00:00Z"
        ),
        RagSourcesCitedEvent(
            run_id="r", sources=[{"id": "1"}], ts="2026-01-01T00:00:00Z"
        ),
        FrontendToolCallRequested(
            run_id="r",
            request_id="q",
            tool_name="t",
            args={},
            ts="2026-01-01T00:00:00Z",
        ),
        FrontendToolCallResponded(
            run_id="r",
            request_id="q",
            result={},
            ts="2026-01-01T00:00:00Z",
        ),
        RunCancelledEvent(
            run_id="r", reason="x", ts="2026-01-01T00:00:00Z"
        ),
    ],
)
def test_event_union_recognizes_new_types(evt: object) -> None:
    adapter = TypeAdapter(Event)
    dumped = evt.model_dump()  # type: ignore[attr-defined]
    restored = adapter.validate_python(dumped)
    assert type(restored) is type(evt)
    assert restored.model_dump() == dumped  # type: ignore[attr-defined]


# 功能：6 个新事件的 type Literal 字段等于 v1 §5.2.1 表格中的 type 字符串
# 设计：分别断言 6 个事件的 type 字符串；type 是 union 判别键，必须与文档一致
def test_new_event_type_literals() -> None:
    assert LlmThinkingEvent(run_id="r", step=0, content="", ts="t").type == "llm.thinking"
    assert (
        ChartRenderedEvent(run_id="r", chart_id="c", option_dict={}, ts="t").type
        == "chart.rendered"
    )
    assert (
        RagSourcesCitedEvent(run_id="r", sources=[], ts="t").type
        == "rag.sources_cited"
    )
    assert (
        FrontendToolCallRequested(
            run_id="r", request_id="q", tool_name="t", args={}, ts="t"
        ).type
        == "frontend.tool_call_requested"
    )
    assert (
        FrontendToolCallResponded(
            run_id="r", request_id="q", result={}, ts="t"
        ).type
        == "frontend.tool_call_responded"
    )
    assert (
        RunCancelledEvent(run_id="r", reason="x", ts="t").type == "run.cancelled"
    )
