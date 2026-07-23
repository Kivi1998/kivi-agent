"""VectorMemoryBackend 端到端集成测试（agent: package-vector-memory-v61）。

仅在 `KIVI_ES_URL` 环境变量已设置时跑（CI 默认跳过，本地启 docker-compose up 后跑）。
覆盖：
- write → read 闭环
- search 召回（knn 命中）
- audit 写入独立索引
"""

from __future__ import annotations

import os
import socket
import uuid

import pytest

from kivi_agent.core.memory import (
    FakeEmbedding,
    VectorBackendConfig,
    VectorMemoryBackend,
)
from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem

# 仅当 KIVI_ES_URL 设置时跑（env guard；CI 跑时无此变量 → 自动 skip）
pytestmark = pytest.mark.skipif(
    "KIVI_ES_URL" not in os.environ,
    reason="KIVI_ES_URL not set; need running Elasticsearch (e.g. docker-compose up)",
)


# 找到一个空闲端口给 ES 测试用（避免与 9200 冲突）；本测试要求 KIVI_ES_URL 已配
@pytest.fixture
def es_url() -> str:
    url = os.environ.get("KIVI_ES_URL", "http://127.0.0.1:9200")
    return url


# 探测 ES 实际可达（否则 pytest skip）
def _es_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        from urllib.parse import urlparse

        u = urlparse(url)
        host = u.hostname or "127.0.0.1"
        port = u.port or 9200
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture
def es_index_name() -> str:
    # 用 UUID 隔离每次测试的索引，避免相互污染
    return f"kivi-memories-test-{uuid.uuid4().hex[:8]}"


# 功能：write → read 闭环能正确往返
# 设计：构造一条 MemoryItem，write 后 read 拿回，断言关键字段一致
@pytest.mark.asyncio
async def test_e2e_write_then_read_roundtrip(es_url: str, es_index_name: str) -> None:
    if not _es_reachable(es_url):
        pytest.skip(f"ES not reachable at {es_url}")
    from elasticsearch import AsyncElasticsearch

    emb = FakeEmbedding(dims=4)
    es = AsyncElasticsearch(hosts=[es_url])
    cfg = VectorBackendConfig(index=es_index_name, audit_index=f"{es_index_name}-audit", dims=4)
    backend = VectorMemoryBackend(embedding=emb, config=cfg, client=es)
    try:
        item = MemoryItem(
            id=f"e2e-{uuid.uuid4().hex[:6]}",
            content="hello e2e world",
            memory_type="user", importance=0.7, status="active",
            created_at="2026-01-01T00:00:00Z",
        )
        await backend.write(item)
        got = await backend.read(item.id)
        assert got is not None
        assert got.id == item.id
        assert got.content == item.content
        assert got.memory_type == "user"
    finally:
        # 清理：删测试索引
        try:
            await es.indices.delete(index=es_index_name, ignore_unavailable=True)
            await es.indices.delete(index=f"{es_index_name}-audit", ignore_unavailable=True)
        finally:
            await es.close()


# 功能：search 能按 knn 召回刚 write 的记忆
# 设计：write 2 条不同内容，搜其中一条，断言能拿到自己
@pytest.mark.asyncio
async def test_e2e_search_knn_recall(es_url: str, es_index_name: str) -> None:
    if not _es_reachable(es_url):
        pytest.skip(f"ES not reachable at {es_url}")
    from elasticsearch import AsyncElasticsearch

    emb = FakeEmbedding(dims=4)
    es = AsyncElasticsearch(hosts=[es_url])
    cfg = VectorBackendConfig(index=es_index_name, audit_index=f"{es_index_name}-audit", dims=4)
    backend = VectorMemoryBackend(embedding=emb, config=cfg, client=es)
    try:
        m1 = MemoryItem(
            id=f"alpha-{uuid.uuid4().hex[:6]}", content="alpha content", memory_type="user",
            importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
        )
        m2 = MemoryItem(
            id=f"bravo-{uuid.uuid4().hex[:6]}", content="bravo content", memory_type="user",
            importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
        )
        await backend.write(m1)
        await backend.write(m2)
        # 同样的输入会得到同样的 hash 向量 → 召回应能命中
        out = await backend.search("alpha content", top_k=2)
        ids = [o.id for o in out]
        assert m1.id in ids
    finally:
        try:
            await es.indices.delete(index=es_index_name, ignore_unavailable=True)
            await es.indices.delete(index=f"{es_index_name}-audit", ignore_unavailable=True)
        finally:
            await es.close()


# 功能：audit 事件落到独立 audit 索引
# 设计：调 audit，refresh 后用 es.get 直接查 audit 索引断言文档存在
@pytest.mark.asyncio
async def test_e2e_audit_event_in_separate_index(es_url: str, es_index_name: str) -> None:
    if not _es_reachable(es_url):
        pytest.skip(f"ES not reachable at {es_url}")
    from elasticsearch import AsyncElasticsearch

    emb = FakeEmbedding(dims=4)
    es = AsyncElasticsearch(hosts=[es_url])
    cfg = VectorBackendConfig(index=es_index_name, audit_index=f"{es_index_name}-audit", dims=4)
    backend = VectorMemoryBackend(embedding=emb, config=cfg, client=es)
    try:
        evt = MemoryAuditEvent(
            memory_id="m-1", event_type="create", ts="2026-01-01T00:00:00Z", actor="user:u-1",
        )
        await backend.audit(evt)
        # 拉审计索引的第 1 条
        await es.indices.refresh(index=f"{es_index_name}-audit")
        # 用 search 而不是 get（因为 audit 写入时没指定 id）
        resp = await es.search(
            index=f"{es_index_name}-audit", size=10, query={"match_all": {}}
        )
        hits = resp.body.get("hits", {}).get("hits", [])
        assert len(hits) >= 1
        src = hits[0]["_source"]
        assert src["memory_id"] == "m-1"
        assert src["event_type"] == "create"
        assert src["actor"] == "user:u-1"
    finally:
        try:
            await es.indices.delete(index=es_index_name, ignore_unavailable=True)
            await es.indices.delete(index=f"{es_index_name}-audit", ignore_unavailable=True)
        finally:
            await es.close()
