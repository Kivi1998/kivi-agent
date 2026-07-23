"""VectorMemoryBackend：ES 8.x + knn 向量检索后端（agent: package-vector-memory-v61）。

设计要点：
- 实现 `MemoryBackend` Protocol（write/read/search/update/delete/audit）
- knn 召回 → top_k → 可选 BM25 重排序
- ES 不可用时（连接失败 / 索引不存在 / 超时）fallback 到 LocalMemoryBackend，记 warn 日志
- id / 索引名路径遍历保护：禁止 `..` / `/` / `\\` / 起始点
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from elastic_transport import ConnectionError as TransportConnectionError
from elastic_transport import ConnectionTimeout
from elasticsearch import AsyncElasticsearch, NotFoundError

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryBackend, MemoryItem
from kivi_agent.core.memory.embedding import EmbeddingProvider
from kivi_agent.core.memory.local_backend import LocalMemoryBackend

log = logging.getLogger(__name__)

# 默认索引名（v1 §T3 + C §6.1 阶段 6 文档契约）
DEFAULT_INDEX = "kivi-memories"
# 审计日志独立索引（与主索引解耦，便于独立查询/保留策略）
DEFAULT_AUDIT_INDEX = "kivi-memory-audit"
# 默认向量维度（text-embedding-3-small 支持 256/512/1024/1536/3072；本项目用 384 占位）
DEFAULT_DIMS = 384

# id / 索引名合法字符：字母 / 数字 / `-` / `_` / `.`；首字符必须为字母或数字
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]*$")


# 把 MemoryItem 序列化为 ES 文档（不含 embedding；embedding 单独建字段）
def _memory_to_doc(memory: MemoryItem, source: str | None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "id": memory.id,
        "content": memory.content,
        "memory_type": memory.memory_type,
        "importance": memory.importance,
        "status": memory.status,
        "created_at": memory.created_at,
    }
    if memory.expires_at is not None:
        doc["expires_at"] = memory.expires_at
    if source is not None:
        doc["source"] = source
    return doc


# 把 ES 文档（_source）反序列化为 MemoryItem；缺字段给默认值
def _doc_to_memory(doc: dict[str, Any]) -> MemoryItem | None:
    if "id" not in doc:
        return None
    return MemoryItem(
        id=str(doc["id"]),
        content=str(doc.get("content", "")),
        memory_type=str(doc.get("memory_type", "user")),
        importance=float(doc.get("importance", 0.5)),
        status=str(doc.get("status", "active")),
        created_at=str(doc.get("created_at", "")),
        expires_at=doc.get("expires_at"),
    )


# 向量后端构造参数（让 __init__ 不超 100 列；也方便 dataclass 复用）
@dataclass
class VectorBackendConfig:
    """VectorMemoryBackend 构造参数（agent: package-vector-memory-v61）。"""

    es_url: str = "http://localhost:9200"
    es_api_key: str | None = None
    index: str = DEFAULT_INDEX
    audit_index: str = DEFAULT_AUDIT_INDEX
    dims: int = DEFAULT_DIMS
    timeout_s: float = 5.0
    # fallback 目标（默认走 LocalMemoryBackend；测试可注入 spy）
    fallback: MemoryBackend | None = None


# ES 向量检索后端；ES 不可用时自动 fallback 到 fallback（默认 Local）
class VectorMemoryBackend:
    """ES 8.x + knn 向量检索后端（agent: package-vector-memory-v61）。

    实现 MemoryBackend Protocol；ES 失败时 fallback 到 LocalMemoryBackend。
    """

    # 初始化：es client / embedding provider / 配置；client=None 时按 cfg.es_url 构造
    def __init__(
        self,
        embedding: EmbeddingProvider,
        config: VectorBackendConfig | None = None,
        client: AsyncElasticsearch | None = None,
    ) -> None:
        self._embedding = embedding
        self.cfg = config or VectorBackendConfig()
        # 客户端：注入优先；未注入则按 es_url 构造一个
        self._client: AsyncElasticsearch = client or AsyncElasticsearch(
            hosts=[self.cfg.es_url],
            api_key=self.cfg.es_api_key,
            request_timeout=self.cfg.timeout_s,
        )
        self._owns_client = client is None
        # fallback 目标：默认走本地 Markdown 后端
        self._fallback: MemoryBackend = self.cfg.fallback or LocalMemoryBackend()

    # 关闭 ES 客户端（仅当自管时调；注入的 client 由调用方负责）
    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()

    # 路径遍历保护：校验 id / 索引名合法字符；非法抛 ValueError
    @staticmethod
    def _check_safe_id(name: str, kind: str) -> None:
        if not name or not _SAFE_ID_RE.match(name):
            raise ValueError(
                f"invalid {kind}: {name!r} (allowed: A-Za-z0-9, leading alnum, no path separators)"
            )

    # 懒加载建索引：索引不存在时按 mapping 创建；存在则 no-op
    async def _ensure_index(self) -> None:
        try:
            exists = await self._client.indices.exists(index=self.cfg.index)
            if exists:
                return
        except (TransportConnectionError, ConnectionTimeout) as exc:
            raise _ESUnavailable(f"ES connect failed: {exc}") from exc

        mapping = {
            "properties": {
                "content": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": self.cfg.dims,
                    "index": True,
                    "similarity": "cosine",
                },
                "memory_type": {"type": "keyword"},
                "importance": {"type": "float"},
                "status": {"type": "keyword"},
                "created_at": {"type": "date"},
                "expires_at": {"type": "date"},
                "source": {"type": "keyword"},
            }
        }
        try:
            await self._client.indices.create(
                index=self.cfg.index, mappings=mapping
            )
        except (TransportConnectionError, ConnectionTimeout) as exc:
            raise _ESUnavailable(f"ES create index failed: {exc}") from exc

    # write: embed content → index 文档（用 memory.id 作为 ES _id）
    async def write(self, memory: MemoryItem) -> str:
        self._check_safe_id(memory.id, "memory id")
        try:
            await self._ensure_index()
            vectors = await self._embedding.embed([memory.content])
            doc = _memory_to_doc(memory, source=None)
            doc["embedding"] = vectors[0]
            await self._client.index(
                index=self.cfg.index, id=memory.id, document=doc, refresh="wait_for"
            )
            return memory.id
        except _ESUnavailable as exc:
            log.warning("vector backend write fallback to local: %s", exc)
            return await self._fallback.write(memory)
        except (TransportConnectionError, ConnectionTimeout) as exc:
            log.warning("vector backend write fallback to local: %s", exc)
            return await self._fallback.write(memory)

    # read: 按 id 取文档 → 反序列化为 MemoryItem
    async def read(self, memory_id: str) -> MemoryItem | None:
        self._check_safe_id(memory_id, "memory id")
        try:
            resp = await self._client.get(index=self.cfg.index, id=memory_id)
            return _doc_to_memory(resp.body.get("_source", {}))
        except NotFoundError:
            return None
        except (TransportConnectionError, ConnectionTimeout) as exc:
            log.warning("vector backend read fallback to local: %s", exc)
            return await self._fallback.read(memory_id)

    # search: embed query → knn 召回 top_k → 可选 BM25 rerank
    async def search(
        self,
        query: str,
        top_k: int = 5,
        reranker: Callable[[str, list[MemoryItem], int], list[MemoryItem]] | None = None,
    ) -> list[MemoryItem]:
        if not query or top_k <= 0:
            return []
        try:
            await self._ensure_index()
            vectors = await self._embedding.embed([query])
            knn_body: dict[str, Any] = {
                "field": "embedding",
                "query_vector": vectors[0],
                "k": top_k,
                "num_candidates": max(top_k * 10, 50),
            }
            resp = await self._client.search(
                index=self.cfg.index,
                knn=knn_body,
                size=top_k,
                source_excludes=["embedding"],
            )
            hits = resp.body.get("hits", {}).get("hits", [])
            items: list[MemoryItem] = []
            for h in hits:
                src = h.get("_source", {})
                item = _doc_to_memory(src)
                if item is not None:
                    items.append(item)
            if reranker is not None and items:
                return reranker(query, items, top_k)
            return items
        except (TransportConnectionError, ConnectionTimeout, _ESUnavailable) as exc:
            log.warning("vector backend search fallback to local: %s", exc)
            return await self._fallback.search(query, top_k)

    # update: 覆盖文档（embedding 重新计算）
    async def update(self, memory_id: str, memory: MemoryItem) -> None:
        self._check_safe_id(memory_id, "memory id")
        try:
            await self._ensure_index()
            vectors = await self._embedding.embed([memory.content])
            doc = _memory_to_doc(memory, source=None)
            doc["embedding"] = vectors[0]
            await self._client.index(
                index=self.cfg.index, id=memory_id, document=doc, refresh="wait_for"
            )
        except _ESUnavailable as exc:
            log.warning("vector backend update fallback to local: %s", exc)
            await self._fallback.update(memory_id, memory)
        except (TransportConnectionError, ConnectionTimeout) as exc:
            log.warning("vector backend update fallback to local: %s", exc)
            await self._fallback.update(memory_id, memory)

    # delete: 按 id 删文档；id 不存在时为幂等操作
    async def delete(self, memory_id: str) -> None:
        self._check_safe_id(memory_id, "memory id")
        try:
            await self._client.delete(
                index=self.cfg.index, id=memory_id, refresh="wait_for"
            )
        except NotFoundError:
            return
        except (TransportConnectionError, ConnectionTimeout) as exc:
            log.warning("vector backend delete fallback to local: %s", exc)
            await self._fallback.delete(memory_id)

    # audit: 审计事件写入独立 audit_index；ES 失败时不 fallback（审计可丢但不能错）
    async def audit(self, event: MemoryAuditEvent) -> None:
        self._check_safe_id(event.memory_id, "memory id")
        doc = {
            "memory_id": event.memory_id,
            "event_type": event.event_type,
            "ts": event.ts,
            "actor": event.actor,
        }
        try:
            await self._client.index(
                index=self.cfg.audit_index, document=doc, refresh="wait_for"
            )
        except (TransportConnectionError, ConnectionTimeout) as exc:
            log.warning("vector backend audit dropped: %s", exc)


# 内部标记异常（让上层 except 收口时统一处理 fallback 路径）
class _ESUnavailable(Exception):
    """ES 不可用时抛此异常以便上层走 fallback（agent: package-vector-memory-v61）。"""

    pass


__all__ = [
    "DEFAULT_AUDIT_INDEX",
    "DEFAULT_DIMS",
    "DEFAULT_INDEX",
    "VectorBackendConfig",
    "VectorMemoryBackend",
]
