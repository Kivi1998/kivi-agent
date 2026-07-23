from __future__ import annotations

from textual.widgets import Static

from kivi_agent.core.bus.events import RagSourcesCitedEvent
from kivi_agent.tui.citation_widget import CitationWidget


# 收集 widget compose() 生成的所有 Static 子节点的 content 文本
def _collect_static_texts(widget: CitationWidget) -> list[str]:
    return [child.content for child in widget.compose() if isinstance(child, Static)]


# 功能：验证 widget 在 sources 含 3 条时正确渲染 header（计数 + run_id）和 3 条引用行
# 设计：直接构造 RagSourcesCitedEvent 喂入 widget，把 compose() 物化成 list 后取每个
#      Static 的 .content，断言首行有 "3 条"、后续 3 行每行带 [1]/[2]/[3] 编号；
#      避免起 Textual App，纯结构化断言，匹配 plan_dialog/ask_user_dialog 测试风格
def test_citation_widget_renders_sources() -> None:
    event = RagSourcesCitedEvent(
        run_id="run-rag-1",
        sources=[
            {"id": "kb-001", "title": "RAG 系统架构综述", "score": 0.95},
            {"id": "kb-002", "title": "企业内部知识库最佳实践", "score": 0.92},
            {"id": "kb-003", "title": "RAG 评估方法", "score": 0.88},
        ],
        ts="2026-07-23T00:00:00Z",
    )
    widget = CitationWidget(event)

    texts = _collect_static_texts(widget)

    # header + 3 source lines
    assert len(texts) == 4
    assert "3 条" in texts[0]
    assert "run_id=run-rag-1" in texts[0]
    assert "[1]" in texts[1]
    assert "[2]" in texts[2]
    assert "[3]" in texts[3]
    # 每行都包含源内容（id 或 title 至少出现一个）
    assert "kb-001" in texts[1] or "RAG 系统架构综述" in texts[1]
    assert "kb-002" in texts[2] or "企业内部知识库最佳实践" in texts[2]


# 功能：验证 sources 为空时 widget 仍能渲染，只显示 header 不显示任何 source 行
# 设计：空 sources 是合法状态（rag 业务可能命中空结果），TUI 不能崩；
#      断言 compose() 只产出 1 个 Static（header），避免无意义的空行
def test_citation_widget_empty_sources() -> None:
    event = RagSourcesCitedEvent(run_id="run-rag-empty", sources=[], ts="t")
    widget = CitationWidget(event)

    texts = _collect_static_texts(widget)

    assert len(texts) == 1
    assert "0 条" in texts[0]
    assert "run_id=run-rag-empty" in texts[0]

