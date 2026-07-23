"""RAG 引用展示 widget（agent: package-tui-output-v2）。

展示 RagSourcesCitedEvent 的 sources 列表（每条是 dict：id / title / score 等）。
每条引用一行，基础版只展示，不做点击展开。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Static

from kivi_agent.core.bus.events import RagSourcesCitedEvent


# 把单条 RAG source dict 序列化为一行可读文本
def _format_source(src: dict[str, Any]) -> str:
    # 优先用 title，其次用 id，再退回到 repr
    if "title" in src:
        return f"title={src['title']!r}"
    if "id" in src:
        return f"id={src['id']!r}"
    return repr(src)


class CitationWidget(Container):
    """RAG 引用展示 widget：header + 每条 source 一行。"""

    DEFAULT_CSS = """
    CitationWidget {
        height: auto;
        border: round cyan;
        padding: 0 1;
    }
    CitationWidget > .citation-header {
        color: cyan;
        text-style: bold;
    }
    CitationWidget > .citation-source {
        color: $text;
    }
    """

    # 初始化：缓存事件对象、生成稳定 widget id
    def __init__(self, event: RagSourcesCitedEvent) -> None:
        super().__init__(id=f"citation-{event.run_id}")
        self._event = event

    # 组合子 Static：header 计数行 + 每条 source 一行
    def compose(self) -> Iterable[Widget]:
        sources = self._event.sources
        yield Static(
            f"📚 引用 ({len(sources)} 条)  run_id={self._event.run_id}",
            classes="citation-header",
        )
        for idx, src in enumerate(sources, 1):
            yield Static(f"  [{idx}] {_format_source(src)}", classes="citation-source")
