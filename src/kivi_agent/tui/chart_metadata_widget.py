"""ECharts 图表元数据展示 widget（agent: package-tui-output-v2）。

TUI mock 展示 ChartRenderedEvent 的 option_dict（图表类型 + 维度 + 度量）。
真实渲染由 Web 端负责（D 阶段）。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Static

from kivi_agent.core.bus.events import ChartRenderedEvent


# 截断过长的 option_dict 字符串避免撑爆 TUI 行宽
def _truncate_option(option_dict: dict[str, Any], max_len: int = 500) -> str:
    option_str = json.dumps(option_dict, ensure_ascii=False, indent=2)
    if len(option_str) > max_len:
        return option_str[:max_len] + "\n... (truncated)"
    return option_str


class ChartMetadataWidget(Container):
    """ECharts 元数据展示 widget：chart_id + type + option dict 文本。"""

    DEFAULT_CSS = """
    ChartMetadataWidget {
        height: auto;
        border: round magenta;
        padding: 0 1;
    }
    ChartMetadataWidget > .chart-title {
        color: magenta;
        text-style: bold;
    }
    ChartMetadataWidget > .chart-meta {
        color: $text-muted;
    }
    ChartMetadataWidget > .chart-option {
        color: $text;
    }
    """

    # 初始化：缓存事件对象、生成稳定 widget id
    def __init__(self, event: ChartRenderedEvent) -> None:
        super().__init__(id=f"chart-{event.run_id}")
        self._event = event

    # 组合子 Static：标题行 + 元信息行 + option dict 文本
    def compose(self) -> Iterable[Widget]:
        option = self._event.option_dict
        chart_type = option.get("type", "unknown") if isinstance(option, dict) else "unknown"
        yield Static(
            f"📊 图表: {self._event.chart_id}  type={chart_type}",
            classes="chart-title",
        )
        yield Static(f"  run_id={self._event.run_id}", classes="chart-meta")
        if not isinstance(option, dict):
            yield Static(f"  (invalid option: {option!r})", classes="chart-option")
            return
        yield Static(_truncate_option(option), classes="chart-option")
