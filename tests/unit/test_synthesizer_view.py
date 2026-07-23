from __future__ import annotations

import asyncio

from textual.app import App
from textual.widgets import Static

from kivi_agent.core.agents.synthesizer import SubResult, SynthesizedResult
from kivi_agent.tui.synthesizer_view import SynthesizerView


# 用 Textual test app 挂载 widget，递归收集所有 Static 子节点 content 文本
# 设计：SynthesizerView 用 VerticalScroll 包裹 final_output，
#      `with VerticalScroll()` 上下文需要活动 app 才能正确建立父子关系；
#      用 run_test() 是 Textual 官方推荐的单 widget 测试方式
def _collect_static_texts(widget: SynthesizerView) -> list[str]:
    out: list[str] = []

    class _Host(App):
        def compose(self) -> None:
            yield widget

    async def _run() -> None:
        host = _Host()
        async with host.run_test() as pilot:
            for child in widget.walk_children():
                if isinstance(child, Static):
                    out.append(child.content)
            await pilot.pause()

    asyncio.run(_run())
    return out


# 功能：验证 2 个 SubResult 时 widget header 正确显示 sub_results=2 + 2 条 bullet 行
# 设计：构造 SynthesizedResult 喂入 widget，把 walk_children 走一遍收集所有 Static，
#      断言 ① header 含 "sub_results=2"
#          ② 两个 SubResult profile_name 各出现 1 次，bullet 标记 "•" 出现 2 次
#      覆盖 plan §4.4 "Synthesizer 汇总" 阶段的核心路径
def test_synth_view_sub_results() -> None:
    result = SynthesizedResult(
        final_output="综合答案",
        sub_results=[
            SubResult(
                profile_name="web_search",
                output="RAG 最新文章要点 1",
                citations=[],
                charts=[],
                trace_ids=["run-web-1"],
            ),
            SubResult(
                profile_name="rag",
                output="内部知识库要点 2",
                citations=["kb-001", "kb-002"],
                charts=[],
                trace_ids=["run-rag-1"],
            ),
        ],
    )
    widget = SynthesizerView(result)

    texts = _collect_static_texts(widget)

    joined = "\n".join(texts)
    assert "sub_results=2" in joined
    assert joined.count("•") == 2
    assert "web_search" in joined
    assert "rag" in joined
    # rag 子结果有 2 个 citation → 展示 "citations=2"
    assert "citations=2" in joined
    # web_search 子结果 0 citation → 展示 "citations=0"
    assert "citations=0" in joined


# 功能：验证 final_output 文本正确渲染在 "📌 最终答案" 之后
# 设计：构造 SynthesizedResult(final_output=...) 喂入 widget，断言
#      ① "📌 最终答案" marker 出现
#      ② final_output 的完整字符串出现在某个 Static.content 里
#      覆盖"最终答案面板"的核心展示
def test_synth_view_final_output() -> None:
    final_text = "综合网上文章和内部知识库，建议采用 hybrid retrieval + bge-reranker。"
    result = SynthesizedResult(final_output=final_text)
    widget = SynthesizerView(result)

    texts = _collect_static_texts(widget)

    joined = "\n".join(texts)
    assert "📌 最终答案" in joined
    assert final_text in joined


# 功能：验证 sources / charts 透传计数正确展示为 "sources=N charts=M"
# 设计：构造 SynthesizedResult 注入 sources=5, charts=2 + 空 sub_results，
#      断言 meta 行文本 "sources=5 charts=2" 出现在 walk_children 输出里；
#      覆盖 synthesizer flatten 后的引用 / 图表计数展示分支
def test_synth_view_sources_charts_count() -> None:
    result = SynthesizedResult(
        final_output="",
        sources=[("web_search", "src-1"), ("rag", "kb-1"), ("rag", "kb-2"),
                 ("web_search", "src-2"), ("rag", "kb-3")],  # 5
        charts=[{"type": "bar"}, {"type": "line"}],  # 2
        sub_results=[],
    )
    widget = SynthesizerView(result)

    texts = _collect_static_texts(widget)

    joined = "\n".join(texts)
    assert "sources=5" in joined
    assert "charts=2" in joined
    # 空 sub_results 时 header 也得正确
    assert "sub_results=0" in joined

