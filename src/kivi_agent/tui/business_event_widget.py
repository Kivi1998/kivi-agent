"""业务事件流展示 widget（agent: package-tui-events-v2）。

订阅 BusinessEventHandler，按事件类型分桶实时展示 v1 §5.2.1 冻结的 6 类业务事件：

- ``LlmThinkingEvent``         → 💭 thinking  (灰色折叠摘要)
- ``RagSourcesCitedEvent``     → 📚 citation  (青色，展示来源数 + 前 3 条)
- ``ChartRenderedEvent``       → 📊 chart     (洋红，option_dict 类型 + chart_id)
- ``FrontendToolCallRequested``→ 🔧 tool req  (黄色)
- ``FrontendToolCallResponded``→ 🔧 tool resp (黄色)
- ``RunCancelledEvent``        → ⛔ cancelled (红色加粗)

设计要点：

- 只读 widget：只 ``pull`` BusinessEventLog 的内容，不直接订阅 EventBus（订阅由主 agent 在
  ``tui/app.py`` 集中编排，避免 widget 与全局事件总线耦合）。主 agent 可通过周期性
  ``refresh_log()`` 或事件回调触发本 widget 重渲染。
- ``Container + VerticalScroll + Static`` 组合：与 ``tui/app.py`` 既有 ``KamaTuiApp`` /
  ``SessionListScreen`` 的范式保持一致；Static 作为整段富文本承载，VerticalScroll 在事件
  变长时自动滚动。
- 颜色 / 图标映射集中在 CSS 与 ``_EVENT_*`` 常量里；与 ``ToolCallBlock`` 一样遵循"分类 CSS class"
  的渲染约定。
- 不知道具体 ``option_dict`` 内部 schema（ECharts schema 自由），只展示 ``type`` 字段作为摘要。

集成位置（备忘给主 agent，见 ``docs/迁移记录/wave2-tui-demo-plan.md`` §5）：

- ``tui/app.py`` 启动时实例化 ``BusinessEventHandler(bus)``，存为 ``self._business_handler``；
- 收到 ``run.started`` 时调 ``handler.start(parent_run_id)`` 然后
  ``mount(BusinessEventWidget(...))``；
- 收到 ``run.finished`` / ``run.cancelled`` 时调 ``handler.stop()`` 释放 log。
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widgets import Static

from kivi_agent.core.bus.events import (
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    RunCancelledEvent,
)
from kivi_agent.core.bus.handlers.business import BusinessEventHandler, BusinessEventLog

# thinking 摘要最大长度（避免一行过长撑爆面板）
_THINKING_PREVIEW_CHARS = 200
# citation 摘要最多展示的来源条数
_CITATION_PREVIEW_LIMIT = 3


# 业务事件流展示 widget：实时拉取 BusinessEventLog 内容并按类型分桶渲染
class BusinessEventWidget(Container):
    """业务事件流展示 widget：实时拉取 ``BusinessEventLog`` 内容并按类型分桶渲染。

    通过 ``handler`` 的 ``get_log(parent_run_id)`` 接口拉取当前 log，每次
    ``refresh_log()`` 触发时整段重新渲染。挂载到 App 后，主 agent 可在
    ``run.started`` 时 ``start(parent_run_id)``，在 ``run.finished`` /
    ``run.cancelled`` 时 ``handler.stop()`` 释放 log。
    """

    DEFAULT_CSS = """
    BusinessEventWidget {
        height: auto;
        border: round blue;
        padding: 0 1;
    }
    BusinessEventWidget > .event-header {
        color: cyan;
        padding: 0 1;
    }
    BusinessEventWidget > VerticalScroll {
        height: auto;
        max-height: 20;
        padding: 0 1;
    }
    BusinessEventWidget .event-thinking {
        color: $text-muted;
    }
    BusinessEventWidget .event-citation {
        color: cyan;
    }
    BusinessEventWidget .event-chart {
        color: magenta;
    }
    BusinessEventWidget .event-frontend {
        color: yellow;
    }
    BusinessEventWidget .event-cancel {
        color: red;
        text-style: bold;
    }
    """

    # 初始化 widget：绑定 handler 与 parent_run_id；id 用 parent_run_id 区分多实例
    def __init__(self, handler: BusinessEventHandler, parent_run_id: str) -> None:
        super().__init__(id=f"event-widget-{parent_run_id}")
        self._handler = handler
        self._parent_run_id = parent_run_id
        # 缓存当前 log 引用；handler 释放后置 None，避免 widget 仍持有过期 log
        self._log: BusinessEventLog | None = self._handler.get_log(parent_run_id)

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), classes="event-header")
        with VerticalScroll():
            yield Static(self._render_log(), id=f"event-log-{self._parent_run_id}")

    # 头部标题文本：标识当前 widget 绑定的 parent run
    def _header_text(self) -> str:
        return f"📡 业务事件流  parent_run_id={self._parent_run_id}"

    # 整段渲染当前 log 的内容；log 不存在 / 为空时给明确提示
    def _render_log(self) -> str:
        # 每次重渲染都重新取一次 log 引用，避免 handler 释放后 widget 缓存失效
        log = self._handler.get_log(self._parent_run_id)
        if log is None:
            return "[dim]no log[/dim]"
        lines: list[str] = []
        # 1) LlmThinkingEvent：折叠式摘要（前 200 字 + step）
        for ev_thinking in log.thinking_traces:
            content = (getattr(ev_thinking, "content", "") or "")[:_THINKING_PREVIEW_CHARS]
            step = getattr(ev_thinking, "step", "?")
            lines.append(f"[dim]💭 thinking[/dim]  step={step}  {content!r}")
        # 2) RagSourcesCitedEvent：来源条数 + 前 3 条标题/ID 摘要
        for ev_citation in log.rag_citations:
            sources: list[Any] = getattr(ev_citation, "sources", None) or []
            preview = ", ".join(_format_source(s) for s in sources[:_CITATION_PREVIEW_LIMIT])
            tail = f"  | {preview}" if preview else ""
            lines.append(f"[cyan]📚 citation[/cyan]  {len(sources)} sources{tail}")
        # 3) ChartRenderedEvent：chart_id + option_dict.type 摘要
        for ev_chart in log.chart_metadata:
            chart_id = getattr(ev_chart, "chart_id", "(no-id)")
            option: Any = getattr(ev_chart, "option_dict", None) or {}
            chart_type = option.get("type", "unknown") if isinstance(option, dict) else "?"
            lines.append(f"[magenta]📊 chart[/magenta]  {chart_id}  type={chart_type}")
        # 4) FrontendToolCall* / RunCancelledEvent：按 sub_events 桶逐条展示
        for run_id, evs in log.sub_events.items():
            for ev in evs:
                if isinstance(ev, FrontendToolCallRequested):
                    tool_name = getattr(ev, "tool_name", "?")
                    lines.append(
                        f"[yellow]🔧 frontend tool req[/yellow]  "
                        f"run_id={run_id}  tool={tool_name}"
                    )
                elif isinstance(ev, FrontendToolCallResponded):
                    request_id = getattr(ev, "request_id", "?")
                    lines.append(
                        f"[yellow]🔧 frontend tool resp[/yellow]  "
                        f"run_id={run_id}  request_id={request_id}"
                    )
                elif isinstance(ev, RunCancelledEvent):
                    reason = getattr(ev, "reason", "?")
                    lines.append(
                        f"[red bold]⛔ cancelled[/red bold]  "
                        f"run_id={run_id}  reason={reason}"
                    )
        return "\n".join(lines) if lines else "[dim]no events yet[/dim]"

    # 重新拉取 log 并刷新内部 Static widget；handler 释放后变为 no-op
    def refresh_log(self) -> None:
        self._log = self._handler.get_log(self._parent_run_id)
        try:
            log_widget = self.query_one(f"#event-log-{self._parent_run_id}", Static)
        except Exception:
            # widget 尚未挂载 / 已卸载（卸载过程中 query_one 可能抛 NoMatches）
            return
        log_widget.update(self._render_log())


# 格式化单条 source dict：优先 title，其次 id，最后回退到 repr
def _format_source(source: object) -> str:
    if isinstance(source, dict):
        title = source.get("title")
        if title:
            return str(title)
        sid = source.get("id")
        if sid:
            return str(sid)
    return repr(source)[:64]


__all__ = ["BusinessEventWidget"]
