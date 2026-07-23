"""rag-kb 真实模式 E2E（agent: package-e2e-real-v4）。

WT-F4 E2E 场景：用 ``InProcessRagKbServer`` 模拟 rag-kb 服务，
通过 ``httpx`` 验证 ``/api/v1/search`` 与 ``/health`` 端点行为。

4 个场景：
1. ``test_rag_real_search_returns_answer_and_sources`` — 搜索返回 answer + sources
2. ``test_rag_real_health_endpoint_ok`` — /health 返回 200 + kb_id
3. ``test_rag_real_search_with_kb_id_in_payload`` — payload 含 kb_id 时回显
4. ``test_rag_real_fallback_when_server_stopped`` — server 关闭后请求失败

依赖：仅 fastapi / uvicorn / httpx（pyproject dev 组已声明）。
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.fixtures.rag_kb_mock_server import DEFAULT_MOCK_DOCS


# 功能：POST /api/v1/search 返回 answer + 至少 2 条 sources + rewritten_query 含原 query
# 设计：用 httpx 直连 mock server 验证 rag-kb REST 契约（answer / sources / rewritten_query
#      三字段是 Wave 4 RagKbClient.search() 的输出形状），断言 source 数量与默认 mock docs 一致
def test_rag_real_search_returns_answer_and_sources(rag_server: str) -> None:
    payload = {"query": "什么是 RAG", "kb_id": "test"}
    resp = httpx.post(f"{rag_server}/api/v1/search", json=payload, timeout=2.0)
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "RAG" in data["answer"]
    assert "sources" in data
    assert len(data["sources"]) == len(DEFAULT_MOCK_DOCS)
    assert "rewritten_query" in data
    assert "什么是 RAG" in data["rewritten_query"]


# 功能：GET /health 返回 200 + status=ok + kb_id 与启动配置一致
# 设计：rag_server fixture 启动 kb_id=default 的 mock；断言响应字段与
#      RagKbClient.health_check() 的期望格式对齐（status bool 化 + kb_id 透传）
def test_rag_real_health_endpoint_ok(rag_server: str) -> None:
    resp = httpx.get(f"{rag_server}/health", timeout=2.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["kb_id"] == "default"


# 功能：payload 含 kb_id 时，rewritten_query 追加 @kb[kb_id] 标签便于追溯
# 设计：发送 kb_id="custom-kb" 验证后端把 kb_id 透传到 rewritten_query，
#      这是 RagQueryTool 失败降级时区分 KB 边界的辅助信号
def test_rag_real_search_with_kb_id_in_payload(rag_server: str) -> None:
    payload = {"query": "向量检索", "kb_id": "custom-kb"}
    resp = httpx.post(f"{rag_server}/api/v1/search", json=payload, timeout=2.0)
    assert resp.status_code == 200
    data = resp.json()
    assert "@kb[custom-kb]" in data["rewritten_query"]


# 功能：server 停止后 httpx 请求失败（连接被拒），模拟 rag-kb 不可用场景
# 设计：直接构造 InProcessRagKbServer 不用 fixture；start → success → stop →
#      再次 GET /health 期望连接失败（httpx.ConnectError），验证
#      RagKbClient 在 server 关闭时的"真实失败"信号，而非"成功但空响应"
def test_rag_real_fallback_when_server_stopped() -> None:
    from tests.fixtures.rag_kb_mock_server import InProcessRagKbServer

    server = InProcessRagKbServer()
    base_url = server.start()
    # 启动后能正常访问
    resp = httpx.get(f"{base_url}/health", timeout=2.0)
    assert resp.status_code == 200
    # 停止 server
    server.stop()
    # 给 OS 一点时间释放端口
    time.sleep(0.3)
    # 再次请求：连接被拒（rag-kb 真挂了的语义）
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{base_url}/health", timeout=1.0)
