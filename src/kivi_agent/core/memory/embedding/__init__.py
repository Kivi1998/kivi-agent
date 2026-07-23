"""Embedding 抽象与实现（agent: package-vector-memory-v61）。

对外暴露 `EmbeddingProvider` 协议 + `FakeEmbedding` / `OpenAICompatEmbedding` 两个
具体实现，供 `VectorMemoryBackend` 在 write/search 时把文本转成向量。
"""

from kivi_agent.core.memory.embedding.fake import FakeEmbedding
from kivi_agent.core.memory.embedding.openai_compat import OpenAICompatEmbedding
from kivi_agent.core.memory.embedding.protocol import EmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "FakeEmbedding",
    "OpenAICompatEmbedding",
]
