"""rag_query 业务 Tool 测试（agent: package-c-v1）。

覆盖：
- Tool 协议：name / category / input_schema 正确
- 返回结构：含 answer / sources / rewritten_query
- sources 至少 2 条，字段齐全（id / title / snippet / score）
- 引用格式：answer 末尾含 <ref_json>{...}</ref_json> 标签
- knowledge_base_id 可选；提供时进入 ref_json
- 参数校验：缺 query 返回 schema_error
- 单测内部步骤：_mock_query_rewrite / _mock_retrieval 行为正确
"""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError

from kivi_agent.core.business.rag_query import (
    MockSource,
    RagQueryTool,
    _format_citation,
    _mock_query_rewrite,
    _mock_retrieval,
)
from kivi_agent.core.tools.base import ToolResult


# 功能：rag_query Tool 协议字段正确
def test_rag_query_tool_metadata() -> None:
    tool = RagQueryTool()
    assert tool.name == "rag_query"
    assert tool.category == "read"
    assert "query" in tool.input_schema["required"]
    assert "knowledge_base_id" in tool.input_schema["properties"]


# 功能：调用返回 answer / sources / rewritten_query 三个字段
async def test_rag_query_returns_expected_keys() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "RAG 是什么？"})
    assert not result.is_error
    data = json.loads(result.content)
    assert "answer" in data
    assert "sources" in data
    assert "rewritten_query" in data


# 功能：sources 至少 2 条，字段齐全
async def test_rag_query_returns_at_least_two_sources() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "anything"})
    data = json.loads(result.content)
    assert len(data["sources"]) >= 2
    for src in data["sources"]:
        assert "id" in src
        assert "title" in src
        assert "snippet" in src
        assert "score" in src


# 功能：rewritten_query 包含 [refined] 后缀（演示版约定）
async def test_rag_query_rewritten_query_has_refined_suffix() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "测试"})
    data = json.loads(result.content)
    assert "[refined]" in data["rewritten_query"]


# 功能：answer 文本末尾含 <ref_json>{...}</ref_json> 标签（C 报告 §3.6 复用 aigroup 格式）
async def test_rag_query_answer_ends_with_ref_json_tag() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "X"})
    data = json.loads(result.content)
    answer = data["answer"]
    # 必须以 </ref_json> 结尾
    assert answer.endswith("</ref_json>")
    # 必须含至少一个 <ref_json>{...}</ref_json> 块
    pattern = r"<ref_json>(\{.*?\})</ref_json>"
    matches = re.findall(pattern, answer, re.DOTALL)
    assert len(matches) >= 1
    # ref_json 内容可解析
    ref_obj = json.loads(matches[-1])
    assert "sources" in ref_obj
    assert "query" in ref_obj


# 功能：answer 中含 <知识片段> XML 标签（C 报告 §3.6 复用 aigroup 文本格式）
async def test_rag_query_answer_contains_knowledge_chunk_xml() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "X"})
    data = json.loads(result.content)
    answer = data["answer"]
    # 每条 source 对应一个 <知识片段> 块
    chunk_pattern = r"<知识片段 \[\d+\][^>]*>.*?</知识片段>"
    chunks = re.findall(chunk_pattern, answer, re.DOTALL)
    assert len(chunks) >= 2


# 功能：knowledge_base_id 注入到 rewritten_query 与 ref_json
async def test_rag_query_knowledge_base_id_propagation() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "X", "knowledge_base_id": "kb-42"})
    data = json.loads(result.content)
    assert "kb-42" in data["rewritten_query"]
    # source id 也带 kb 标签
    assert all("kb-42" in src["id"] for src in data["sources"])


# 功能：缺 query 返回 schema_error
async def test_rag_query_missing_query_returns_schema_error() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：query 类型错误也返回 schema_error
async def test_rag_query_invalid_query_type() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": 999})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：参数校验——knowledge_base_id 非 str 时报错
async def test_rag_query_kb_id_must_be_string() -> None:
    tool = RagQueryTool()
    result = await tool.invoke({"query": "X", "knowledge_base_id": 123})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：_mock_query_rewrite 内部实现
def test_mock_query_rewrite_appends_refined() -> None:
    assert "[refined]" in _mock_query_rewrite("test", None)
    # knowledge_base_id 非空时进入后缀
    out = _mock_query_rewrite("test", "kb1")
    assert "kb1" in out


# 功能：_mock_retrieval 至少返回 2 条，score 0-1 之间
def test_mock_retrieval_shape() -> None:
    sources = _mock_retrieval("any", None)
    assert len(sources) >= 2
    for s in sources:
        assert isinstance(s, MockSource)
        assert 0.0 <= s.score <= 1.0


# 功能：_format_citation 返回 (answer_text, ref_json) 元组
def test_format_citation_structure() -> None:
    sources = [
        MockSource(id="a", title="t1", snippet="s1", score=0.9, url="u1"),
        MockSource(id="b", title="t2", snippet="s2", score=0.8, url="u2"),
    ]
    answer_text, ref_json_str = _format_citation("query", sources)
    # 末尾必须是 </ref_json>
    assert answer_text.endswith("</ref_json>")
    # ref_json_str 可解析
    obj = json.loads(ref_json_str)
    assert obj["query"] == "query"
    assert len(obj["sources"]) == 2


# 功能：Pydantic RagQueryParams 直接校验
def test_rag_query_params_validation() -> None:
    from kivi_agent.core.business.rag_query import RagQueryParams

    p = RagQueryParams.model_validate({"query": "x", "knowledge_base_id": "kb1"})
    assert p.query == "x"
    assert p.knowledge_base_id == "kb1"
    # knowledge_base_id 可省略
    p2 = RagQueryParams.model_validate({"query": "x"})
    assert p2.knowledge_base_id is None
    # query 必填
    with pytest.raises(ValidationError):
        RagQueryParams.model_validate({})
