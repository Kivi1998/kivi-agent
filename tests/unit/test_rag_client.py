"""RagKbClient 单元测试（agent: package-rag-real-v4）。

覆盖 6 场景（任务书 Step 5）：
- search 成功（httpx MockTransport 返回正确 schema）
- search HTTP 错误（4xx/5xx → RagKbError）
- search 超时（httpx.TimeoutException → RagKbError）
- search schema 不匹配（缺字段 / 非 JSON → RagKbError）
- health_check 正常（200 → True）
- health_check 不可用（网络错误 → False，不抛错）

设计要点：
- 用 httpx.MockTransport 注入 fake 响应（无需起真实服务，CI 离线）
- 6 个测试都跑同一个 client 实例 + 同一 transport handler（按测试场景切换 handler）
- 不依赖任何环境变量 / 网络 / 端口
"""

from __future__ import annotations

import httpx
import pytest

from kivi_agent.core.rag.client import RagKbClient, RagKbError
from kivi_agent.core.rag.types import RagSearchResult


# 工厂：构造带 MockTransport 的 RagKbClient（agent: package-rag-real-v4）
def _make_client(handler) -> RagKbClient:
    return RagKbClient(base_url="http://rag-kb-test", _transport=httpx.MockTransport(handler))


# 功能：search 成功时返回 RagSearchResult，字段全对
# 设计：用 httpx.MockTransport 返回 200 + 标准 schema JSON；
#       直接断言 result 是 RagSearchResult 且字段值匹配（不 mock search() 自身）
async def test_search_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/search"
        return httpx.Response(
            200,
            json={
                "answer": "RAG 是检索增强生成。",
                "rewritten_query": "what is rag [refined]",
                "sources": [
                    {
                        "id": "kb-001",
                        "title": "RAG 综述",
                        "snippet": "检索增强生成...",
                        "score": 0.92,
                        "url": "https://kb.example.com/rag",
                    },
                ],
            },
        )

    client = _make_client(handler)
    result = await client.search(query="what is rag")
    assert isinstance(result, RagSearchResult)
    assert result.answer == "RAG 是检索增强生成。"
    assert result.rewritten_query == "what is rag [refined]"
    assert len(result.sources) == 1
    assert result.sources[0].id == "kb-001"
    assert result.sources[0].score == 0.92
    await client.close()


# 功能：search 返回 4xx/5xx 时抛 RagKbError
# 设计：mock 500 响应；raise_for_status 会包成 HTTPError，client.search 再包成 RagKbError；
#       验证错误信息含 "rag-kb search failed" 便于排障
async def test_search_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "internal"})

    client = _make_client(handler)
    with pytest.raises(RagKbError, match="rag-kb search failed"):
        await client.search(query="x")
    await client.close()


# 功能：search 超时时抛 RagKbError（包成统一的错误类型）
# 设计：httpx.TimeoutException 是 HTTPError 子类，client.search 应统一包成 RagKbError；
#       避免上层要 try except 多种 httpx 异常
async def test_search_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    client = _make_client(handler)
    with pytest.raises(RagKbError, match="rag-kb search failed"):
        await client.search(query="x")
    await client.close()


# 功能：search 响应 schema 不匹配时抛 RagKbError
# 设计：mock 缺 "answer" 字段的响应（KeyError 路径），客户端应包成 RagKbError；
#       验证错误信息含 "rag-kb response schema mismatch" 便于排障
async def test_search_schema_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 缺 answer 字段，触发 KeyError
        return httpx.Response(200, json={"sources": []})

    client = _make_client(handler)
    with pytest.raises(RagKbError, match="rag-kb response schema mismatch"):
        await client.search(query="x")
    await client.close()


# 功能：health_check 200 返回 True
# 设计：mock 200 + 简单 JSON body；客户端只看 status_code == 200；
#       不抛错
async def test_health_check_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    client = _make_client(handler)
    assert await client.health_check() is True
    await client.close()


# 功能：health_check 网络错误返回 False（不抛错）
# 设计：mock ConnectError 模拟服务未起；客户端必须吞掉异常返回 False
#       （健康检查调用方需要"软失败"语义，不能让 health_check 本身挂掉）
async def test_health_check_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _make_client(handler)
    assert await client.health_check() is False
    await client.close()
