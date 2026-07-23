"""长期记忆子包入口（agent: package-vector-memory-v61）。

对外暴露：
- v1 已有的 LocalMemoryBackend / MemoryStore / 抽取/召回/Loader
- Wave 6.1 新增的 VectorMemoryBackend（ES 8.x + knn + fallback）
- EmbeddingProvider + FakeEmbedding / OpenAICompatEmbedding
- BM25Reranker（简单版 TF-IDF + cosine）
"""

from kivi_agent.core.memory.embedding import (
    EmbeddingProvider,
    FakeEmbedding,
    OpenAICompatEmbedding,
)
from kivi_agent.core.memory.loader import load_context_file
from kivi_agent.core.memory.local_backend import LocalMemoryBackend
from kivi_agent.core.memory.rerank import BM25Reranker
from kivi_agent.core.memory.store import MemoryEntry, MemoryStore
from kivi_agent.core.memory.vector_backend import (
    DEFAULT_AUDIT_INDEX,
    DEFAULT_DIMS,
    DEFAULT_INDEX,
    VectorBackendConfig,
    VectorMemoryBackend,
)

__all__ = [
    "BM25Reranker",
    "DEFAULT_AUDIT_INDEX",
    "DEFAULT_DIMS",
    "DEFAULT_INDEX",
    "EmbeddingProvider",
    "FakeEmbedding",
    "LocalMemoryBackend",
    "MemoryEntry",
    "MemoryStore",
    "OpenAICompatEmbedding",
    "VectorBackendConfig",
    "VectorMemoryBackend",
    "load_context_file",
]
