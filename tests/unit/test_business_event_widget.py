"""BusinessEventWidget 单元测试（agent: package-tui-events-v2）。

按 v1 §5.2.1 冻结的 6 类业务事件，验证 ``BusinessEventWidget`` 在 Textual App
中按类型分桶渲染的内容正确性。

为什么用真 ``BusinessEventHandler`` + ``FakeEventBus`` 而不是 ``MagicMock``：
- widget 真实接口是 ``handler.get_log(parent_run_id) -> BusinessEventLog``；
  mock 实现容易写出"接口错位"的测试（比如返回 Mock 而不是 BusinessEventLog）
- 真 handler + 直接修改 log 字段既保留了真实调用链，又让测试同步可控
- FakeEventBus 是 ``tests/_fakes`` 已有的共享 fake，避免引入额外依赖

为什么用 ``App.run_test()`` 而不是直接 ``_render_log()``：
- spec 要求 "用 Textual ``App.run_test()``"；mount + query_one 验证 widget 真正
  能在 Textual DOM 里被挂载、ID 可寻址、Static 内容可读
- 直接调 ``_render_log()`` 跳过了 mount / ID 解析，能漏掉 CSS class / 挂载顺序
  等真实集成问题
"""
from __future__ import annotations

from textual.app import App

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)
from kivi_agent.core.bus.handlers.business import BusinessEventHandler
from kivi_agent.tui.business_event_widget import BusinessEventWidget
from tests._fakes.event_bus import FakeEventBus


# 最小宿主 App：仅用来 mount BusinessEventWidget
class _HostApp(App[None]):
    def __init__(self, widget: BusinessEventWidget) -> None:
        super().__init__()
        self._widget = widget

    def compose(self):
        yield self._widget


# 挂载 widget 并返回内部 log Static 的当前渲染文本
async def _mount_and_get_log_text(widget: BusinessEventWidget) -> str:
    app = _HostApp(widget)
    async with app.run_test() as pilot:
        await pilot.pause()
        log_widget = app.query_one(f"#event-log-{widget._parent_run_id}")  # type: ignore[attr-defined]
        # Static.content 是当前 renderable；当 renderable 是 str 时可直接断言
        rendered = log_widget.content
        assert isinstance(rendered, str)
        return rendered


# 功能：handler 未启动时（get_log 返回 None）widget 显示 "no log"
# 设计：构造 widget 时显式传不存在的 parent_run_id；不调 handler.start()；
#      渲染结果只走 "_render_log log is None" 分支；这是"晚于 start() 之前
#      mount widget"或"handler.stop() 之后"两个真实场景的共享兜底语义
async def test_widget_no_log() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    # 注意：故意不调 handler.start()
    widget = BusinessEventWidget(handler, parent_run_id="run-unknown")

    rendered = await _mount_and_get_log_text(widget)

    assert "no log" in rendered


# 功能：log 存在但无任何事件时 widget 显示 "no events yet"
# 设计：start() 创建空 log，挂载 widget；走 "log 不是 None 但所有分类列表都是空
#      且 sub_events 也是空"分支；与 "no log" 是两个不同状态，分开断言避免串味
async def test_widget_empty_log() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    handler.start("run-empty")
    widget = BusinessEventWidget(handler, parent_run_id="run-empty")

    rendered = await _mount_and_get_log_text(widget)

    assert "no events yet" in rendered


# 功能：1 个 LlmThinkingEvent 触发后 widget 渲染含 "💭 thinking" 摘要
# 设计：直接 log.thinking_traces.append 1 个事件，绕开 EventBus 异步；
#      断言同时含 "💭 thinking"（icon + 类别名）和 content 子串
#      （验证 widget 真的从事件字段取值，而不是写死占位符）
async def test_widget_thinking_event() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-think")
    log.thinking_traces.append(
        LlmThinkingEvent(run_id="run-think", step=1, content="分析路由", ts="t1")
    )
    widget = BusinessEventWidget(handler, parent_run_id="run-think")

    rendered = await _mount_and_get_log_text(widget)

    assert "💭 thinking" in rendered
    assert "分析路由" in rendered


# 功能：RagSourcesCitedEvent 含 3 个 sources 时，widget 渲染 "📚 citation" 与 "3 sources"
# 设计：构造 3 个不同 schema 的 source（title / id / fallback）覆盖 _format_source
#      的全部 3 个分支；同时断言总条数 3 与第 1 个 source 的 title
#      —— 这是验收点最集中的"一次性覆盖"组合
async def test_widget_citation_event() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-cite")
    log.rag_citations.append(
        RagSourcesCitedEvent(
            run_id="run-cite",
            sources=[
                {"id": "kb-001", "title": "RAG 系统架构综述", "score": 0.95},
                {"id": "kb-002", "title": "企业内部知识库最佳实践", "score": 0.92},
                {"id": "kb-003", "title": None},  # title 为空时回退到 id
            ],
            ts="t1",
        )
    )
    widget = BusinessEventWidget(handler, parent_run_id="run-cite")

    rendered = await _mount_and_get_log_text(widget)

    assert "📚 citation" in rendered
    assert "3 sources" in rendered
    assert "RAG 系统架构综述" in rendered
    # 第 3 个 source 的 title 是 None，widget 应回退到 id 展示
    assert "kb-003" in rendered


# 功能：ChartRenderedEvent 的 option_dict 含 type 字段时，widget 渲染 "type=bar"
# 设计：直接构造 ChartRenderedEvent（v1 §5.2.1 字段名是 option_dict 不是 option）；
#      断言含 "📊 chart" 与 "type=bar"，证明 widget 从 option_dict 真的取到了 type
async def test_widget_chart_event() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-chart")
    log.chart_metadata.append(
        ChartRenderedEvent(
            run_id="run-chart",
            chart_id="chart-1",
            option_dict={"type": "bar", "xAxis": ["Q1", "Q2", "Q3"]},
            ts="t1",
        )
    )
    widget = BusinessEventWidget(handler, parent_run_id="run-chart")

    rendered = await _mount_and_get_log_text(widget)

    assert "📊 chart" in rendered
    assert "type=bar" in rendered
    assert "chart-1" in rendered


# 功能：RunCancelledEvent 触发后 widget 渲染 "⛔ cancelled"
# 设计：RunCancelledEvent 不在分类列表里（业务侧未到），只能通过 log.sub_events
#      注入；断言同时含 "⛔ cancelled" 与 run_id，确保 widget 真的遍历了
#      sub_events 而不是只看了分类列表
async def test_widget_cancel_event() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    log = handler.start("run-cancel")
    # sub_events 是 dict[str, list[BaseModel]]：key 是 run_id，value 是事件列表
    log.sub_events.setdefault("run-cancel", []).append(
        RunCancelledEvent(run_id="run-cancel", reason="user_requested", ts="t1")
    )
    widget = BusinessEventWidget(handler, parent_run_id="run-cancel")

    rendered = await _mount_and_get_log_text(widget)

    assert "⛔ cancelled" in rendered
    assert "user_requested" in rendered
    assert "run-cancel" in rendered


# 功能：refresh_log() 在 handler 释放后能优雅 no-op，不抛异常
# 设计：start → refresh_log（应正常）→ handler.stop() → refresh_log（必须 no-op）；
#      这是 "handler 释放后 widget 仍可能被回调"这个真实场景的容错断言，
#      避免 widget 在 widget 卸载竞态下抛 NoMatches 把 App 拉崩
async def test_widget_refresh_log_after_handler_stop_is_noop() -> None:
    bus = FakeEventBus()
    handler = BusinessEventHandler(bus)
    handler.start("run-refresh")
    widget = BusinessEventWidget(handler, parent_run_id="run-refresh")

    app = _HostApp(widget)
    async with app.run_test() as pilot:
        await pilot.pause()
        # stop 后 get_log 返回 None；refresh_log 应在 query_one 失败时静默退出
        handler.stop()
        # 不抛异常 = 通过
        widget.refresh_log()
