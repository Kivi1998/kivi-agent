"""echarts_render 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 冻结名 = echarts_render（旧名 chart_render 已弃用）。
按 C 报告 §3.9 决议：Tool 只返回 ECharts option dict（不绑定前端版本），
不引入 ECharts JavaScript 到后端。前端由 D 阶段用 v5.x 渲染。

演示版内置 5 种 chart_type 模板（bar / line / pie / scatter / heatmap），
依据 C 报告 §3.9 演示版约定 + 任务书 T5 决议。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.tools.base import ToolResult

# echarts_render 支持的图表类型（演示版 5 种）
SUPPORTED_CHART_TYPES: tuple[str, ...] = ("bar", "line", "pie", "scatter", "heatmap")


# echarts_render 输入参数（agent: package-c-v1）
class EchartsRenderParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rows: list[dict[str, object]] = Field(min_length=1)  # 至少 1 行
    # Literal 自动生成 JSON schema enum；Pydantic 自动拒绝非枚举值
    chart_type: Literal["bar", "line", "pie", "scatter", "heatmap"] = "bar"


# echarts_render 业务 Tool：演示版内置 5 种模板（agent: package-c-v1）
class EchartsRenderTool(BaseBusinessTool):
    """echarts_render Tool：返回 ECharts option dict。

    演示版：
    - 输入：rows（list[dict]）+ chart_type（可选，默认 bar）
    - 输出：{option: {...}} —— ECharts 配置 dict
    - 5 种 chart_type 模板：bar / line / pie / scatter / heatmap

    真实实现：调 ECharts service（aigroup echart_api_url），
    或用 LLM 生成 chart metadata 后填充模板。演示版直接模板填充。
    """

    # 支持的图表类型
    supported_chart_types: ClassVar[tuple[str, ...]] = SUPPORTED_CHART_TYPES

    params_model = EchartsRenderParams
    name = "echarts_render"
    category = "read"  # 纯函数，无副作用
    description = (
        "Render an ECharts option dict from tabular data. "
        "Returns a complete ECharts v5-compatible 'option' object that can be "
        "fed to echarts.init(dom).setOption(option) on the frontend. "
        "Supported chart types: bar (default), line, pie, scatter, heatmap. "
        "The first column of 'rows' is used as the category axis (X axis), "
        "remaining numeric columns are series data."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "object"},
                "minItems": 1,
                "description": (
                    "Tabular data as a list of row dicts. "
                    "The first column (by dict key order) is treated as the category axis."
                ),
            },
            "chart_type": {
                "type": "string",
                "enum": list(SUPPORTED_CHART_TYPES),
                "default": "bar",
                "description": "Chart type. One of: bar, line, pie, scatter, heatmap.",
            },
        },
        "required": ["rows"],
    }

    # 演示版入口（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = EchartsRenderParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),
                is_error=True,
                error_type="schema_error",
            )
        # chart_type 白名单（即便 Pydantic 已校验，也双保险）
        if p.chart_type not in SUPPORTED_CHART_TYPES:
            return ToolResult(
                content=json.dumps(
                    {
                        "error": "unsupported_chart_type",
                        "supported": list(SUPPORTED_CHART_TYPES),
                        "got": p.chart_type,
                    },
                    ensure_ascii=False,
                ),
                is_error=True,
                error_type="runtime_error",
            )
        option = _build_option(p.rows, p.chart_type)
        return ToolResult(
            content=json.dumps({"option": option, "chart_type": p.chart_type}, ensure_ascii=False)
        )


# 演示版 ECharts option 模板（agent: package-c-v1）
# 设计：5 种 chart_type 模板 + 从 rows 提取 X 轴 + 系列数据
def _build_option(rows: list[dict[str, object]], chart_type: str) -> dict[str, Any]:
    """根据 chart_type 生成 ECharts option dict。

    rows 结构假设：list[dict]，所有 dict 共享同一组 key。
    第一个 key 当 X 轴（category），其余 numeric 列当 series data。
    """
    if not rows:
        # Pydantic 已校验 min_length=1，此处仅作防御
        return _empty_option(chart_type)
    # 提取 keys（按 dict 出现顺序，Python 3.7+ dict 保序）
    first_row = rows[0]
    keys = list(first_row.keys())
    if not keys:
        return _empty_option(chart_type)
    x_key = keys[0]
    y_keys = keys[1:] if len(keys) > 1 else [x_key]  # 至少 1 个 series
    x_data = [str(row.get(x_key, "")) for row in rows]
    # 按 chart_type 走不同模板
    if chart_type == "bar":
        return _bar_template(x_data, y_keys, rows)
    if chart_type == "line":
        return _line_template(x_data, y_keys, rows)
    if chart_type == "pie":
        return _pie_template(x_data, y_keys, rows)
    if chart_type == "scatter":
        return _scatter_template(x_data, y_keys, rows)
    if chart_type == "heatmap":
        return _heatmap_template(x_data, y_keys, rows)
    # 兜底：bar
    return _bar_template(x_data, y_keys, rows)


# 空 option（防御性，理论上 Pydantic 拦得住 rows=[]）
def _empty_option(chart_type: str) -> dict[str, Any]:
    return {
        "title": {"text": "Empty Data"},
        "xAxis": {"type": "category", "data": []},
        "yAxis": {"type": "value"},
        "series": [{"type": chart_type if chart_type in SUPPORTED_CHART_TYPES else "bar", "data": []}],
    }


# 提取 series 数据的辅助函数
def _extract_series_data(rows: list[dict[str, object]], y_keys: list[str]) -> list[list[Any]]:
    """返回 [series1_values, series2_values, ...] —— 每条 series 一列。"""
    series_data: list[list[Any]] = []
    for y_key in y_keys:
        series_data.append([row.get(y_key, 0) for row in rows])
    return series_data


# 1. bar 模板
def _bar_template(
    x_data: list[str], y_keys: list[str], rows: list[dict[str, object]]
) -> dict[str, Any]:
    series_data = _extract_series_data(rows, y_keys)
    return {
        "title": {"text": "Bar Chart (Mock)"},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_keys},
        "xAxis": {"type": "category", "data": x_data},
        "yAxis": {"type": "value"},
        "series": [
            {"name": y_key, "type": "bar", "data": data}
            for y_key, data in zip(y_keys, series_data, strict=False)
        ],
    }


# 2. line 模板
def _line_template(
    x_data: list[str], y_keys: list[str], rows: list[dict[str, object]]
) -> dict[str, Any]:
    series_data = _extract_series_data(rows, y_keys)
    return {
        "title": {"text": "Line Chart (Mock)"},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_keys},
        "xAxis": {"type": "category", "data": x_data},
        "yAxis": {"type": "value"},
        "series": [
            {"name": y_key, "type": "line", "data": data, "smooth": True}
            for y_key, data in zip(y_keys, series_data, strict=False)
        ],
    }


# 3. pie 模板
def _pie_template(
    x_data: list[str], y_keys: list[str], rows: list[dict[str, object]]
) -> dict[str, Any]:
    # pie 用第一列当 name，第二列当 value（演示版只取第一个 y_key）
    if y_keys:
        values = [row.get(y_keys[0], 0) for row in rows]
    else:
        values = []
    pie_data = [{"name": name, "value": val} for name, val in zip(x_data, values, strict=False)]
    return {
        "title": {"text": "Pie Chart (Mock)"},
        "tooltip": {"trigger": "item", "formatter": "{a} <br/>{b}: {c} ({d}%)"},
        "legend": {"data": x_data},
        "series": [
            {
                "name": y_keys[0] if y_keys else "value",
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": pie_data,
            }
        ],
    }


# 4. scatter 模板
def _scatter_template(
    x_data: list[str], y_keys: list[str], rows: list[dict[str, object]]
) -> dict[str, Any]:
    # scatter 用 [x_value, y_value] 对
    scatter_series: list[dict[str, Any]] = []
    for y_key in y_keys:
        points = [[row.get(x_data[0] if x_data else "x", 0), row.get(y_key, 0)] for row in rows]
        scatter_series.append({"name": y_key, "type": "scatter", "data": points, "symbolSize": 12})
    return {
        "title": {"text": "Scatter Chart (Mock)"},
        "tooltip": {"trigger": "item"},
        "legend": {"data": y_keys},
        "xAxis": {"type": "value"},
        "yAxis": {"type": "value"},
        "series": scatter_series,
    }


# 5. heatmap 模板
def _heatmap_template(
    x_data: list[str], y_keys: list[str], rows: list[dict[str, object]]
) -> dict[str, Any]:
    # heatmap 数据是 [x_index, y_index, value] 三元组
    heatmap_data: list[list[Any]] = []
    for x_idx, row in enumerate(rows):
        for y_idx, y_key in enumerate(y_keys):
            heatmap_data.append([x_idx, y_idx, row.get(y_key, 0)])
    return {
        "title": {"text": "Heatmap Chart (Mock)"},
        "tooltip": {"position": "top"},
        "grid": {"left": "10%", "right": "10%", "bottom": "15%"},
        "xAxis": {"type": "category", "data": x_data, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": y_keys, "splitArea": {"show": True}},
        "visualMap": {"min": 0, "max": 100, "calculable": True, "orient": "horizontal"},
        "series": [{"name": "Heatmap", "type": "heatmap", "data": heatmap_data}],
    }
