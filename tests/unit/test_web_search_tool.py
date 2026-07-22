"""web_search 业务 Tool 测试（agent: package-c-v1）。

覆盖：
- Tool 协议：name / category / input_schema 正确
- Mock 行为：调用返回 3 条结果，字段齐全（id / title / url / snippet / source）
- 字段值：source 固定为 mock-tavily，title/snippet 含用户 query
- 参数校验：缺 query 返回 schema_error
- category 正确标记为 read（无副作用）
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from kivi_agent.core.business.web_search import WebSearchTool
from kivi_agent.core.tools.base import ToolResult


# 功能：web_search Tool 协议字段正确
def test_web_search_tool_metadata() -> None:
    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.category == "read"
    assert isinstance(tool.input_schema, dict)
    assert tool.input_schema["required"] == ["query"]
    assert "query" in tool.input_schema["properties"]


# 功能：调用返回 3 条结果，结构完整
async def test_web_search_returns_three_results() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": "Python 异步编程"})
    assert isinstance(result, ToolResult)
    assert not result.is_error
    data = json.loads(result.content)
    assert isinstance(data, list)
    assert len(data) == 3


# 功能：每条结果字段齐全：id / title / url / snippet / source
async def test_web_search_result_fields_complete() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": "AI agent"})
    data = json.loads(result.content)
    for item in data:
        assert "id" in item
        assert "title" in item
        assert "url" in item
        assert "snippet" in item
        assert "source" in item


# 功能：source 字段固定为 mock-tavily（按 C 报告 §3.1 演示版约定）
async def test_web_search_source_is_mock_tavily() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": "foo"})
    data = json.loads(result.content)
    for item in data:
        assert item["source"] == "mock-tavily"


# 功能：title 和 snippet 包含用户 query（让 LLM 看到 query 参与了 mock 生成）
async def test_web_search_includes_query_in_results() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": "RAG 检索增强生成"})
    data = json.loads(result.content)
    for item in data:
        assert "RAG 检索增强生成" in item["title"] or "RAG 检索增强生成" in item["snippet"]


# 功能：id 唯一且为字符串
async def test_web_search_ids_unique() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": "x"})
    data = json.loads(result.content)
    ids = [item["id"] for item in data]
    assert len(set(ids)) == 3
    for i in ids:
        assert isinstance(i, str)


# 功能：缺 query 返回 schema_error（Pydantic ValidationError 包装）
async def test_web_search_missing_query_returns_schema_error() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：query 为非字符串类型同样触发 schema_error
async def test_web_search_invalid_query_type() -> None:
    tool = WebSearchTool()
    result = await tool.invoke({"query": 123})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：Pydantic model 直接校验亦工作（双保险）
def test_web_search_params_validation() -> None:
    from kivi_agent.core.business.web_search import WebSearchParams

    p = WebSearchParams.model_validate({"query": "hello"})
    assert p.query == "hello"
    with pytest.raises(ValidationError):
        WebSearchParams.model_validate({})
