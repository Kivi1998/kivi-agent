"""rag_query Tool 真实模式 vs Mock 模式集成测试（agent: package-rag-real-v4）。

覆盖 3 场景（任务书 Step 5）：
- real 模式：注入 mock RagKbClient → 验证调 .search() + 返回真实结果
- mock 模式：client=None → 验证完全不发 HTTP 请求
- 降级：client 抛 RagKbError → 自动降级到 mock + 业务继续

设计要点：
- 用 AsyncMock 替换 RagKbClient（无需 httpx，CI 离线 + 跑得快）
- 3 个测试都构造 RagQueryTool(client=...) 验证三种注入路径
- real 模式断言 client.search 被调 1 次 + 用了正确的 query/kb_id
- mock 模式断言 client.search 未被调 + 走的是 _run_mock 路径（用 [refined] 后缀判定）
- fallback 模式断言 client.search 被调 1 次 + 仍然返回 ToolResult（带 [refined] 后缀）
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from kivi_agent.core.business.rag_query import RagQueryTool
from kivi_agent.core.rag.client import RagKbError
from kivi_agent.core.rag.types import RagSearchResult, RagSource


# 功能：real 模式注入 client 时，invoke 调 client.search + 返回真实结果
# 设计：构造 mock client（AsyncMock），调用 invoke 验证：
#       1) client.search 被调 1 次
#       2) 传参 query/kb_id 正确
#       3) 返回的 ToolResult 的 rewritten_query 来自 client（不是 mock 的 [refined] 后缀）
#       4) sources 来自 client（不是 mock 的 "kb-default-001"）
async def test_real_mode_uses_client() -> None:
    # mock client.search 返回预设 RagSearchResult
    mock_client = AsyncMock()
    mock_client.search = AsyncMock(
        return_value=RagSearchResult(
            answer="Real answer from rag-kb",
            rewritten_query="real-query-from-rag-kb",
            sources=[
                RagSource(
                    id="real-1",
                    title="Real KB",
                    snippet="real content",
                    score=0.88,
                    url="https://real.example.com/kb",
                ),
            ],
        )
    )

    tool = RagQueryTool(client=mock_client)
    result = await tool.invoke({"query": "what is rag", "knowledge_base_id": "kb-real"})

    # 1) 验证 mock client 被调
    mock_client.search.assert_awaited_once()
    # 2) 验证传参
    call_kwargs = mock_client.search.await_args.kwargs
    assert call_kwargs["query"] == "what is rag"
    assert call_kwargs["kb_id"] == "kb-real"
    # 3) 验证返回结果来自 client（不是 mock 路径）
    assert not result.is_error
    data = json.loads(result.content)
    # rewritten_query 来自 client（不是 mock 的 [refined] 后缀）
    assert data["rewritten_query"] == "real-query-from-rag-kb"
    assert "[refined]" not in data["rewritten_query"]
    # sources 来自 client
    assert data["sources"][0]["id"] == "real-1"
    assert data["sources"][0]["score"] == 0.88
    # real 路径返回的 source id 不应含 "default"（mock 模式的标志）
    assert "default" not in data["sources"][0]["id"]


# 功能：mock 模式（client=None）时，invoke 完全不调 client
# 设计：构造 RagQueryTool()（无 client），验证：
#       1) 返回的 ToolResult 含 [refined] 后缀（mock 路径特征）
#       2) 不存在 client.search 调用（设计上没有 client 属性）
#       3) 行为与原 mock 工具完全一致（向后兼容）
async def test_mock_mode_skips_client() -> None:
    tool = RagQueryTool()  # 不传 client → mock 模式
    result = await tool.invoke({"query": "测试"})

    assert not result.is_error
    data = json.loads(result.content)
    # mock 路径特征：rewritten_query 必含 [refined] 后缀
    assert "[refined]" in data["rewritten_query"]
    # mock 路径特征：answer 必含 "Mock RAG answer for:"
    assert "Mock RAG answer for:" in data["answer"]
    # mock 路径特征：sources 至少 2 条
    assert len(data["sources"]) >= 2
    # Tool 内部无 client 属性（设计上等于"完全不调外部服务"）
    assert tool._client is None  # noqa: SLF001 — 测试用：验证设计意图


# 功能：real 模式 client 抛 RagKbError 时，自动降级到 mock 业务继续
# 设计：mock client.search 抛 RagKbError，验证：
#       1) client.search 被调 1 次（real 路径真的尝试了）
#       2) ToolResult 不 is_error（业务没挂）
#       3) 返回的 rewritten_query 含 [refined] 后缀（降级到了 mock 路径）
async def test_fallback_on_client_error() -> None:
    mock_client = AsyncMock()
    mock_client.search = AsyncMock(side_effect=RagKbError("rag-kb down"))

    tool = RagQueryTool(client=mock_client)
    result = await tool.invoke({"query": "test"})

    # 1) client.search 被调（real 路径真的尝试了）
    mock_client.search.assert_awaited_once()
    # 2) 业务没挂
    assert not result.is_error
    # 3) 降级到了 mock（rewritten_query 含 [refined] 后缀）
    data = json.loads(result.content)
    assert "[refined]" in data["rewritten_query"]
    assert "Mock RAG answer for:" in data["answer"]
