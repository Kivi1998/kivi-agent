"""echarts_render 业务 Tool 测试（agent: package-c-v1）。

覆盖：
- Tool 协议：name / category / input_schema 正确
- 5 种 chart_type 模板都正确生成（bar / line / pie / scatter / heatmap）
- 默认 chart_type 是 bar
- bar 模板结构完全匹配任务书 T5 描述
- 模板字段一致性：xAxis / yAxis / series 都存在
- 异常：rows 空、chart_type 不支持、参数类型错
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from kivi_agent.core.business.echarts_render import (
    SUPPORTED_CHART_TYPES,
    EchartsRenderTool,
)
from kivi_agent.core.tools.base import ToolResult


# 演示版固定测试数据
SAMPLE_ROWS: list[dict[str, object]] = [
    {"product": "Alpha", "sales": 100, "returns": 5},
    {"product": "Beta", "sales": 200, "returns": 10},
    {"product": "Gamma", "sales": 150, "returns": 8},
]


# 功能：echarts_render Tool 协议字段正确
def test_echarts_render_tool_metadata() -> None:
    tool = EchartsRenderTool()
    assert tool.name == "echarts_render"
    assert tool.category == "read"
    # rows 必填，chart_type 可选
    assert "rows" in tool.input_schema["required"]
    assert "chart_type" not in tool.input_schema["required"]
    # chart_type enum 包含 5 种
    chart_type_enum = tool.input_schema["properties"]["chart_type"]["enum"]
    assert set(chart_type_enum) == {"bar", "line", "pie", "scatter", "heatmap"}


# 功能：5 种 chart_type 模板都能正确生成
@pytest.mark.parametrize("chart_type", ["bar", "line", "pie", "scatter", "heatmap"])
async def test_echarts_render_all_chart_types(chart_type: str) -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": chart_type})
    assert not result.is_error, f"chart_type={chart_type} should not error: {result.content}"
    data = json.loads(result.content)
    assert "option" in data
    assert data["chart_type"] == chart_type
    option = data["option"]
    # 所有模板都必须含 series 字段
    assert "series" in option
    assert isinstance(option["series"], list)
    assert len(option["series"]) >= 1


# 功能：bar 模板结构（任务书 T5 要求完全匹配）
async def test_echarts_render_bar_template() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "bar"})
    data = json.loads(result.content)
    option = data["option"]
    # xAxis type=category, data 含 products
    assert option["xAxis"]["type"] == "category"
    assert option["xAxis"]["data"] == ["Alpha", "Beta", "Gamma"]
    # yAxis 存在
    assert "yAxis" in option
    # series[0] type=bar
    bar_series = [s for s in option["series"] if s["type"] == "bar"]
    assert len(bar_series) >= 1
    # series[0].data 对应 sales
    sales_series = next(s for s in bar_series if s["name"] == "sales")
    assert sales_series["data"] == [100, 200, 150]
    # returns 也应有 series
    returns_series = next(s for s in bar_series if s["name"] == "returns")
    assert returns_series["data"] == [5, 10, 8]


# 功能：line 模板含 smooth=True
async def test_echarts_render_line_template_smooth() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "line"})
    data = json.loads(result.content)
    series_list = data["option"]["series"]
    line_series = [s for s in series_list if s["type"] == "line"]
    assert len(line_series) >= 1
    for s in line_series:
        assert s.get("smooth") is True


# 功能：pie 模板含 name + value 字段
async def test_echarts_render_pie_template() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "pie"})
    data = json.loads(result.content)
    series_list = data["option"]["series"]
    pie_series = [s for s in series_list if s["type"] == "pie"]
    assert len(pie_series) == 1
    pie_data = pie_series[0]["data"]
    assert len(pie_data) == 3
    for item in pie_data:
        assert "name" in item
        assert "value" in item


# 功能：scatter 模板含二维点
async def test_echarts_render_scatter_template() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "scatter"})
    data = json.loads(result.content)
    series_list = data["option"]["series"]
    scatter_series = [s for s in series_list if s["type"] == "scatter"]
    assert len(scatter_series) >= 1
    # 每条 series 至少有一些点
    for s in scatter_series:
        assert "data" in s
        # 点是 [x, y] 形式
        for point in s["data"]:
            assert isinstance(point, list)
            assert len(point) == 2


# 功能：heatmap 模板含 visualMap
async def test_echarts_render_heatmap_template() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "heatmap"})
    data = json.loads(result.content)
    option = data["option"]
    # heatmap 必须含 visualMap
    assert "visualMap" in option
    # series 是 heatmap
    heatmap_series = [s for s in option["series"] if s["type"] == "heatmap"]
    assert len(heatmap_series) == 1
    # 数据是 [x, y, value] 三元组
    for point in heatmap_series[0]["data"]:
        assert isinstance(point, list)
        assert len(point) == 3


# 功能：默认 chart_type 是 bar
async def test_echarts_render_default_chart_type() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["chart_type"] == "bar"


# 功能：缺 rows 返回 schema_error
async def test_echarts_render_missing_rows() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：rows 为空列表返回 schema_error（Pydantic min_length=1）
async def test_echarts_render_empty_rows() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": []})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：rows 不是 list 返回 schema_error
async def test_echarts_render_invalid_rows_type() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": "not a list"})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：chart_type 不在白名单时 Pydantic 拦截
async def test_echarts_render_invalid_chart_type() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": SAMPLE_ROWS, "chart_type": "unknown"})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：所有 5 种 chart_type 都被 SUPPORTED_CHART_TYPES 收录
def test_supported_chart_types_complete() -> None:
    assert set(SUPPORTED_CHART_TYPES) == {"bar", "line", "pie", "scatter", "heatmap"}
    assert len(SUPPORTED_CHART_TYPES) == 5


# 功能：Pydantic 直接校验
def test_echarts_render_params_validation() -> None:
    from kivi_agent.core.business.echarts_render import EchartsRenderParams

    p = EchartsRenderParams.model_validate({"rows": [{"a": 1, "b": 2}]})
    assert p.chart_type == "bar"  # 默认
    p2 = EchartsRenderParams.model_validate({"rows": [{"a": 1}], "chart_type": "line"})
    assert p2.chart_type == "line"
    with pytest.raises(ValidationError):
        EchartsRenderParams.model_validate({"rows": []})
    with pytest.raises(ValidationError):
        EchartsRenderParams.model_validate({"chart_type": "bar"})  # 缺 rows


# 功能：单行数据也能渲染（防御 edge case）
async def test_echarts_render_single_row() -> None:
    tool = EchartsRenderTool()
    result = await tool.invoke({"rows": [{"x": "A", "y": 1}]})
    assert not result.is_error
    data = json.loads(result.content)
    assert "option" in data
