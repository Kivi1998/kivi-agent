from __future__ import annotations

from textual.widgets import Static

from kivi_agent.core.bus.events import ChartRenderedEvent
from kivi_agent.tui.chart_metadata_widget import ChartMetadataWidget, _truncate_option


# 收集 widget compose() 生成的所有 Static 子节点的 content 文本
def _collect_static_texts(widget: ChartMetadataWidget) -> list[str]:
    return [child.content for child in widget.compose() if isinstance(child, Static)]


# 功能：验证 option_dict.type="bar" 时 widget 正确渲染图表类型到标题行
# 设计：直接构造 ChartRenderedEvent 喂入 widget，把 compose() 物化成 list 后取每个
#      Static 的 .content，断言首行包含 "type=bar" + chart_id；
#      覆盖"正常 option dict → 正确显示图表类型"的核心路径
def test_chart_widget_renders_type() -> None:
    event = ChartRenderedEvent(
        run_id="run-db-1",
        chart_id="sales-2026-q1",
        option_dict={
            "type": "bar",
            "xAxis": {"type": "category", "data": ["Q1", "Q2", "Q3"]},
            "series": [{"name": "count", "data": [10, 20, 30]}],
        },
        ts="2026-07-23T00:00:00Z",
    )
    widget = ChartMetadataWidget(event)

    texts = _collect_static_texts(widget)

    # 标题行 + 元信息行 + option 文本行
    assert len(texts) >= 3
    assert "type=bar" in texts[0]
    assert "sales-2026-q1" in texts[0]
    assert "run_id=run-db-1" in texts[1]
    # option 文本被序列化进 compose 的第三个 Static
    assert any('"type": "bar"' in t for t in texts)


# 功能：验证 option_dict 嵌套结构超 500 字符时正确截断并追加 "(truncated)" 提示
# 设计：直接调 _truncate_option 纯函数，构造一个 >500 字符的 dict，断言
#      返回值含 "... (truncated)" 标记且不超过 500 + 14 字符；避免 TUI 行宽被撑爆
def test_chart_widget_truncates_long_option() -> None:
    big_data = [f"item-{i}" for i in range(50)]  # 50 个长字符串塞进 series
    big_option = {
        "type": "line",
        "xAxis": {"data": big_data},
        "series": [{"name": "s", "data": big_data}],
    }

    truncated = _truncate_option(big_option, max_len=500)

    assert truncated.endswith("... (truncated)")
    # 500 字符 + 截断标记 14 字符
    assert len(truncated) <= 500 + len("\n... (truncated)")


# 功能：验证 option_dict 非 dict（兜底：上游传了 None / 字符串 / 数字）时
#      type 显示为 "unknown" 且 option 行不崩溃
# 设计：直接构造 option_dict=None 的事件（Pydantic 允许 dict | None 在 Any 下），
#      断言 compose() 仍产出 2-3 个 Static，标题行 type=unknown；
#      覆盖 plan §5.3 "TUI mock 仅展示 option_dict" 的容错分支
def test_chart_widget_invalid_option() -> None:
    # 用 model_construct 绕过 Pydantic 字段校验，模拟上游 bug
    event = ChartRenderedEvent.model_construct(
        type="chart.rendered",
        run_id="run-bad",
        chart_id="bad-chart",
        option_dict=None,  # type: ignore[arg-type]
        ts="t",
    )
    widget = ChartMetadataWidget(event)

    texts = _collect_static_texts(widget)

    assert len(texts) >= 2
    assert "type=unknown" in texts[0]
    # 不能让 raw None 出现在渲染里，应该用 fallback 字符串
    assert any("invalid option" in t for t in texts)

