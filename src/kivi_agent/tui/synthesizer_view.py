"""Synthesizer 汇总展示 widget（agent: package-tui-output-v2）。

展示 SynthesizedResult：sub_results（每个 Profile 的输出 + 引用 + 图表）
+ sources / charts 透传计数 + final_output 汇总。
"""

from __future__ import annotations

from collections.abc import Iterable

from textual.containers import Container, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from kivi_agent.core.agents.synthesizer import SynthesizedResult


# 截断过长的子 Profile 输出文本以保持 TUI 可读性
def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


class SynthesizerView(Container):
    """Synthesizer 汇总展示 widget：上游 SubResult + 透传计数 + 最终答案。"""

    DEFAULT_CSS = """
    SynthesizerView {
        height: auto;
        border: round green;
        padding: 0 1;
    }
    SynthesizerView > .synth-header {
        color: green;
        text-style: bold;
    }
    SynthesizerView > .sub-result {
        color: $text;
    }
    SynthesizerView > .synth-meta {
        color: $text-muted;
    }
    SynthesizerView > .final-header {
        color: green;
        text-style: bold;
    }
    SynthesizerView > .final-output {
        color: $text;
    }
    """

    # 初始化：缓存合成结果对象
    def __init__(self, result: SynthesizedResult) -> None:
        super().__init__(id="synthesizer-view")
        self._result = result

    # 组合子 Static：header + SubResult 列表 + 透传计数 + 最终答案
    def compose(self) -> Iterable[Widget]:
        yield Static(
            f"🔄 Synthesizer 汇总  sub_results={len(self._result.sub_results)}",
            classes="synth-header",
        )
        # 上游 SubResult 列表：每条一行展示
        for sub in self._result.sub_results:
            yield Static(
                f"  • {sub.profile_name}: {_truncate(sub.output)!r}  "
                f"(citations={len(sub.citations)}, charts={len(sub.charts)})",
                classes="sub-result",
            )
        # 引用 / 图表透传计数
        yield Static(
            f"  sources={len(self._result.sources)}  charts={len(self._result.charts)}",
            classes="synth-meta",
        )
        # 最终答案：用 VerticalScroll 包裹防止超长 final_output 撑爆 TUI
        # 直接以 children 形式 yield（不走 `with` 上下文）以便无 app 测试
        yield VerticalScroll(
            Static("📌 最终答案", classes="final-header"),
            Static(self._result.final_output, classes="final-output"),
            classes="final-scroll",
        )
