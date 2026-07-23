"""EmbeddingProvider 协议（agent: package-vector-memory-v61）。

定义文本 → 向量的统一接口；VectorMemoryBackend 仅依赖本协议，不直接耦合实现。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


# 文本转向量的统一接口；实现需保证 batch 调用与逐条调用结果一致
@runtime_checkable
class EmbeddingProvider(Protocol):
    # 把一批文本映射为同顺序的向量列表（长度由实现决定；VectorMemoryBackend 默认 384 维）
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    # 单条文本便捷方法；默认实现走 batch 再取首条（性能敏感可由子类覆盖）
    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0]


__all__ = ["EmbeddingProvider"]
