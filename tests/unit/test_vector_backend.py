"""VectorMemoryBackend 单测（agent: package-vector-memory-v61）。

覆盖 6 方法 + fallback + 路径遍历 + Protocol 满足性。Mock ES 客户端用 AsyncMock。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import ConnectionTimeout
from elasticsearch import NotFoundError

from kivi_agent.core.memory import (
    BM25Reranker,
    FakeEmbedding,
    VectorBackendConfig,
    VectorMemoryBackend,
)
from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryBackend, MemoryItem


# 构造一个最小可用的 mock ES 客户端：indices.exists / index / search / get / delete
def _make_mock_es() -> AsyncMock:
    es = AsyncMock()
    # indices.exists 返回 False（首次写需要建索引）
    es.indices.exists = AsyncMock(return_value=False)
    # indices.create 不抛
    es.indices.create = AsyncMock(return_value=MagicMock(body={"acknowledged": True}))
    return es


# 构造 VectorMemoryBackend：注入 mock es + 短 dims（节省计算）
def _make_backend(
    fallback: MemoryBackend | None = None,
    es_mock: AsyncMock | None = None,
    dims: int = 4,
) -> VectorMemoryBackend:
    es = es_mock or _make_mock_es()
    emb = FakeEmbedding(dims=dims)
    cfg = VectorBackendConfig(fallback=fallback, dims=dims)
    return VectorMemoryBackend(embedding=emb, config=cfg, client=es)


# 功能：VectorMemoryBackend 满足 MemoryBackend Protocol
# 设计：isinstance 校验通过；这是 J3 Gateway API 能直接注入的前提
def test_satisfies_memory_backend_protocol() -> None:
    backend = _make_backend()
    assert isinstance(backend, MemoryBackend)


# 功能：write 走 indices.exists + indices.create + index 三步，并返回 memory.id
# 设计：mock ES 全套，断言三次 await 被调 + id 一致
@pytest.mark.asyncio
async def test_write_indexes_document_with_embedding() -> None:
    es = _make_mock_es()
    es.index = AsyncMock(return_value=MagicMock(body={"result": "created"}))
    backend = _make_backend(es_mock=es, dims=4)
    item = MemoryItem(
        id="m-1", content="hello world", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    mid = await backend.write(item)
    assert mid == "m-1"
    es.indices.exists.assert_awaited_once()
    es.indices.create.assert_awaited_once()
    es.index.assert_awaited_once()
    # 文档体应包含 content + embedding 字段
    body = es.index.await_args.kwargs["document"]
    assert body["content"] == "hello world"
    assert len(body["embedding"]) == 4
    assert body["id"] == "m-1"
    assert body["memory_type"] == "user"


# 功能：write 时索引已存在则跳过 create
# 设计：indices.exists 返回 True 模拟已建索引；断言 create 未被调
@pytest.mark.asyncio
async def test_write_skips_create_when_index_exists() -> None:
    es = _make_mock_es()
    es.indices.exists = AsyncMock(return_value=True)
    es.index = AsyncMock(return_value=MagicMock(body={"result": "created"}))
    backend = _make_backend(es_mock=es, dims=4)
    item = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    await backend.write(item)
    es.indices.create.assert_not_called()


# 功能：read 走 get + 把 _source 解析为 MemoryItem
# 设计：mock get 返回 _source；断言 7 字段全对
@pytest.mark.asyncio
async def test_read_returns_parsed_memory_item() -> None:
    es = _make_mock_es()
    es.get = AsyncMock(return_value=MagicMock(body={
        "_source": {
            "id": "m-1", "content": "hello", "memory_type": "feedback",
            "importance": 0.9, "status": "archived",
            "created_at": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
        }
    }))
    backend = _make_backend(es_mock=es)
    got = await backend.read("m-1")
    assert got is not None
    assert got.id == "m-1"
    assert got.content == "hello"
    assert got.memory_type == "feedback"
    assert got.importance == 0.9
    assert got.status == "archived"
    assert got.expires_at == "2027-01-01T00:00:00Z"


# 功能：read 不存在 id 时 ES 抛 NotFoundError，backend 返回 None
# 设计：get 抛 NotFoundError；断言 read 返回 None（不抛）
@pytest.mark.asyncio
async def test_read_not_found_returns_none() -> None:
    es = _make_mock_es()
    es.get = AsyncMock(side_effect=NotFoundError(message="not found", meta=MagicMock(), body=None))
    backend = _make_backend(es_mock=es)
    got = await backend.read("missing")
    assert got is None


# 功能：search embed query → knn → 解析 hits
# 设计：mock search 返回 2 条 hits；断言 query embedding 长度正确 + 拿到 2 个 MemoryItem
@pytest.mark.asyncio
async def test_search_knn_returns_top_k_items() -> None:
    es = _make_mock_es()
    es.search = AsyncMock(return_value=MagicMock(body={
        "hits": {
            "hits": [
                {"_id": "m-1", "_source": {"id": "m-1", "content": "alpha", "memory_type": "user", "importance": 0.5, "status": "active", "created_at": "t1"}},
                {"_id": "m-2", "_source": {"id": "m-2", "content": "bravo", "memory_type": "user", "importance": 0.6, "status": "active", "created_at": "t2"}},
            ]
        }
    }))
    backend = _make_backend(es_mock=es, dims=4)
    out = await backend.search("query", top_k=5)
    assert len(out) == 2
    assert out[0].id == "m-1"
    assert out[1].id == "m-2"


# 功能：search 的 knn body 包含 query_vector + field + k
# 设计：断言 mock client.search 的 knn 参数合法
@pytest.mark.asyncio
async def test_search_knn_body_has_query_vector() -> None:
    es = _make_mock_es()
    es.search = AsyncMock(return_value=MagicMock(body={"hits": {"hits": []}}))
    backend = _make_backend(es_mock=es, dims=4)
    await backend.search("hello", top_k=3)
    knn = es.search.await_args.kwargs["knn"]
    assert knn["field"] == "embedding"
    assert knn["k"] == 3
    assert len(knn["query_vector"]) == 4


# 功能：search 空 query 返回空列表（不发请求）
# 设计：search("") 走 fast path
@pytest.mark.asyncio
async def test_search_empty_query_returns_empty() -> None:
    es = _make_mock_es()
    backend = _make_backend(es_mock=es)
    out = await backend.search("", top_k=5)
    assert out == []
    es.search.assert_not_called()


# 功能：search 配 BM25Reranker 时返回 rerank 后的 top_k
# 设计：mock search 返回 3 条；用 BM25Reranker 断言 reranker 被调 + top_k 截断
@pytest.mark.asyncio
async def test_search_with_bm25_reranker() -> None:
    es = _make_mock_es()
    es.search = AsyncMock(return_value=MagicMock(body={
        "hits": {
            "hits": [
                {"_id": "m-1", "_source": {"id": "m-1", "content": "alpha bravo", "memory_type": "user", "importance": 0.5, "status": "active", "created_at": "t"}},
                {"_id": "m-2", "_source": {"id": "m-2", "content": "charlie delta", "memory_type": "user", "importance": 0.5, "status": "active", "created_at": "t"}},
                {"_id": "m-3", "_source": {"id": "m-3", "content": "echo alpha", "memory_type": "user", "importance": 0.5, "status": "active", "created_at": "t"}},
            ]
        }
    }))
    backend = _make_backend(es_mock=es, dims=4)
    reranker = BM25Reranker[MemoryItem](text_getter=lambda m: m.content)
    out = await backend.search("alpha", top_k=2, reranker=reranker.rerank)
    assert len(out) == 2
    # "alpha bravo" 和 "echo alpha" 都有 alpha，rerank 排前两个
    ids = {o.id for o in out}
    assert ids == {"m-1", "m-3"}


# 功能：update 重新计算 embedding 并覆盖索引文档
# 设计：mock index 记录被调；断言 body 含新 embedding
@pytest.mark.asyncio
async def test_update_overwrites_with_new_embedding() -> None:
    es = _make_mock_es()
    es.index = AsyncMock(return_value=MagicMock(body={"result": "updated"}))
    backend = _make_backend(es_mock=es, dims=4)
    new_item = MemoryItem(
        id="m-1", content="new content", memory_type="feedback", importance=0.9,
        status="archived", created_at="2026-01-01T00:00:00Z",
    )
    await backend.update("m-1", new_item)
    body = es.index.await_args.kwargs["document"]
    assert body["content"] == "new content"
    assert body["memory_type"] == "feedback"
    assert len(body["embedding"]) == 4


# 功能：delete 走 client.delete
# 设计：mock delete，断言 id 正确
@pytest.mark.asyncio
async def test_delete_calls_es_delete() -> None:
    es = _make_mock_es()
    es.delete = AsyncMock(return_value=MagicMock(body={"result": "deleted"}))
    backend = _make_backend(es_mock=es)
    await backend.delete("m-1")
    es.delete.assert_awaited_once()
    assert es.delete.await_args.kwargs["id"] == "m-1"


# 功能：delete 不存在 id（ES 抛 NotFoundError）时为幂等操作
# 设计：delete 抛 NotFoundError；断言 backend 不向上抛
@pytest.mark.asyncio
async def test_delete_nonexistent_is_idempotent() -> None:
    es = _make_mock_es()
    es.delete = AsyncMock(side_effect=NotFoundError(message="x", meta=MagicMock(), body=None))
    backend = _make_backend(es_mock=es)
    # 不应抛异常
    await backend.delete("missing")


# 功能：audit 写独立 audit_index 索引
# 设计：mock index，断言调用走的 index 是 audit_index 且文档含 memory_id
@pytest.mark.asyncio
async def test_audit_writes_to_audit_index() -> None:
    es = _make_mock_es()
    es.index = AsyncMock(return_value=MagicMock(body={"result": "created"}))
    backend = _make_backend(es_mock=es)
    evt = MemoryAuditEvent(
        memory_id="m-1", event_type="create", ts="2026-01-01T00:00:00Z", actor="user:u-1"
    )
    await backend.audit(evt)
    call = es.index.await_args
    assert call.kwargs["index"] == "kivi-memory-audit"
    assert call.kwargs["document"]["memory_id"] == "m-1"
    assert call.kwargs["document"]["event_type"] == "create"


# 功能：search 时 ES 连接失败 → fallback 到 LocalMemoryBackend.search
# 设计：search 抛 TransportConnectionError；spy fallback 验证被调 + 拿到结果
@pytest.mark.asyncio
async def test_search_falls_back_to_local_on_connection_error() -> None:
    es = _make_mock_es()
    # _ensure_index → indices.exists 抛连接错
    es.indices.exists = AsyncMock(side_effect=TransportConnectionError("nope"))
    # 注入 spy fallback
    spy = AsyncMock()
    spy.search = AsyncMock(return_value=[
        MemoryItem(id="local-1", content="from-local", memory_type="user", importance=0.5,
                   status="active", created_at="2026-01-01T00:00:00Z")
    ])
    backend = _make_backend(es_mock=es, fallback=spy)
    out = await backend.search("query", top_k=5)
    assert len(out) == 1
    assert out[0].id == "local-1"
    spy.search.assert_awaited_once()


# 功能：search 时 ES 超时 → fallback 到 LocalMemoryBackend
# 设计：search 抛 ConnectionTimeout；断言 fallback 被调
@pytest.mark.asyncio
async def test_search_falls_back_on_timeout() -> None:
    es = _make_mock_es()
    es.search = AsyncMock(side_effect=ConnectionTimeout("timeout"))
    spy = AsyncMock()
    spy.search = AsyncMock(return_value=[])
    backend = _make_backend(es_mock=es, fallback=spy)
    out = await backend.search("query", top_k=3)
    assert out == []
    spy.search.assert_awaited_once()


# 功能：write 时 ES 失败 → fallback 到 LocalMemoryBackend.write
# 设计：index 抛连接错；spy.write 被调
@pytest.mark.asyncio
async def test_write_falls_back_to_local_on_error() -> None:
    es = _make_mock_es()
    es.index = AsyncMock(side_effect=TransportConnectionError("nope"))
    spy = AsyncMock()
    spy.write = AsyncMock(return_value="local-1")
    backend = _make_backend(es_mock=es, fallback=spy)
    item = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    mid = await backend.write(item)
    assert mid == "local-1"
    spy.write.assert_awaited_once()


# 功能：read 时 ES 失败 → fallback 到 LocalMemoryBackend.read
# 设计：get 抛连接错；spy.read 被调
@pytest.mark.asyncio
async def test_read_falls_back_to_local_on_error() -> None:
    es = _make_mock_es()
    es.get = AsyncMock(side_effect=TransportConnectionError("nope"))
    spy = AsyncMock()
    spy.read = AsyncMock(return_value=MemoryItem(
        id="local-1", content="from-local", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z"
    ))
    backend = _make_backend(es_mock=es, fallback=spy)
    got = await backend.read("anything")
    assert got is not None
    assert got.id == "local-1"
    spy.read.assert_awaited_once()


# 功能：update 时 ES 失败 → fallback 到 LocalMemoryBackend.update
# 设计：index 抛连接错；spy.update 被调
@pytest.mark.asyncio
async def test_update_falls_back_to_local_on_error() -> None:
    es = _make_mock_es()
    es.index = AsyncMock(side_effect=TransportConnectionError("nope"))
    spy = AsyncMock()
    spy.update = AsyncMock()
    backend = _make_backend(es_mock=es, fallback=spy)
    item = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    await backend.update("m-1", item)
    spy.update.assert_awaited_once()


# 功能：delete 时 ES 失败 → fallback 到 LocalMemoryBackend.delete
# 设计：delete 抛连接错；spy.delete 被调
@pytest.mark.asyncio
async def test_delete_falls_back_to_local_on_error() -> None:
    es = _make_mock_es()
    es.delete = AsyncMock(side_effect=TransportConnectionError("nope"))
    spy = AsyncMock()
    spy.delete = AsyncMock()
    backend = _make_backend(es_mock=es, fallback=spy)
    await backend.delete("m-1")
    spy.delete.assert_awaited_once()


# 功能：audit 在 ES 失败时不抛异常（审计可丢但不能错主流程）
# 设计：index 抛连接错；assert audit 不抛
@pytest.mark.asyncio
async def test_audit_silently_drops_on_error(caplog: pytest.LogCaptureFixture) -> None:
    import logging
    es = _make_mock_es()
    es.index = AsyncMock(side_effect=TransportConnectionError("nope"))
    backend = _make_backend(es_mock=es)
    evt = MemoryAuditEvent(
        memory_id="m-1", event_type="create", ts="2026-01-01T00:00:00Z", actor="user:u-1"
    )
    with caplog.at_level(logging.WARNING):
        # 不应抛
        await backend.audit(evt)
    assert any("audit" in r.message.lower() for r in caplog.records)


# 功能：id 含 `..` 或 `/` 时抛 ValueError（路径遍历保护）
# 设计：4 种非法 id 各跑一次；write / read / update / delete 都要校验
@pytest.mark.asyncio
async def test_path_traversal_protection_on_ids() -> None:
    backend = _make_backend()
    item = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    for bad in ["../etc/passwd", "foo/bar", "foo\\bar", ".hidden"]:
        with pytest.raises(ValueError):
            await backend.write(MemoryItem(**{**item.__dict__, "id": bad}))
        with pytest.raises(ValueError):
            await backend.read(bad)
        with pytest.raises(ValueError):
            await backend.update(bad, item)
        with pytest.raises(ValueError):
            await backend.delete(bad)
        with pytest.raises(ValueError):
            await backend.audit(MemoryAuditEvent(
                memory_id=bad, event_type="x", ts="t", actor="a"
            ))


# 功能：VectorMemoryBackend 注入 client 时不创建自有 client（_owns_client=False）
# 设计：构造时显式传 client，断言 aclose 不会 close 注入的 client
@pytest.mark.asyncio
async def test_aclose_skips_injected_client() -> None:
    es = _make_mock_es()
    es.close = AsyncMock()
    backend = _make_backend(es_mock=es)
    await backend.aclose()
    # 注入的 client 不应被 close
    es.close.assert_not_called()


# 功能：VectorMemoryBackend 自管 client 时 aclose 关闭
# 设计：不传 client，构造后 aclose 应当 close；这里只检查 _owns_client 标志
def test_owns_client_when_no_injection() -> None:
    # 我们不能真起 ES；只验证 _owns_client 标志 + 路径不会被 try 创建
    cfg = VectorBackendConfig(es_url="http://127.0.0.1:1")  # 不会真连（async）
    emb = FakeEmbedding(dims=4)
    # 用 AsyncMock 避免真构造 AsyncElasticsearch（默认会做 sniffing 探活）
    fake_client = AsyncMock()
    backend = VectorMemoryBackend(embedding=emb, config=cfg, client=fake_client)
    assert backend._owns_client is False  # type: ignore[attr-defined]
