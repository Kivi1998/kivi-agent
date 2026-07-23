"""FakeEmbedding：纯哈希的离线 Embedding 实现（agent: package-vector-memory-v61）。

用 SHA-256 的前 48 字节循环展开到目标维度并 L2 归一化，单测/CI/演示场景使用；
语义质量不重要，确定性 + 零网络依赖才是重点。
"""

from __future__ import annotations

import hashlib
import math


# 把 48 字节 hash 循环展开成 dims 维向量并 L2 归一化（伪随机但稳定）
def _hash_to_vector(text: str, dims: int) -> list[float]:
    # SHA-256 仅 32 字节；用 SHA-512 取前 48 字节保证稳定 + 足量字节展开到 384 维
    digest = hashlib.sha512(text.encode("utf-8")).digest()[:48]
    expanded: list[float] = []
    for i in range(dims):
        # 48 字节循环 → dims 维（每维从 digest 中按 i 索引采样）
        byte = digest[i % 48]
        # 偏移 + 高 7 位保符号 → [-1.0, 1.0] 区间
        val = (byte - 128) / 128.0
        # 加微小偏移避免相邻维度完全相等
        val += (i * 13 % 7 - 3) * 0.001
        expanded.append(val)
    norm = math.sqrt(sum(v * v for v in expanded)) or 1.0
    return [v / norm for v in expanded]


# 用 SHA-256 文本哈希展开到目标维度的伪随机 Embedding（无网络、单测/CI 友好）
class FakeEmbedding:
    # 初始化：可指定目标维度，默认 384 与 VectorMemoryBackend.knn dims 对齐
    def __init__(self, dims: int = 384) -> None:
        if dims <= 0:
            raise ValueError(f"FakeEmbedding dims must be > 0, got {dims}")
        self.dims = dims

    # 批量嵌入：每条文本独立 hash 展开，相同输入永远返回相同向量
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_to_vector(t, self.dims) for t in texts]

    # 单条文本便捷方法（runtime_checkable 要求方法在类上显式存在）
    async def embed_one(self, text: str) -> list[float]:
        return _hash_to_vector(text, self.dims)


__all__ = ["FakeEmbedding"]
