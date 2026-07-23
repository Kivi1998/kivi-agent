"""语义去重器（Wave 6.1 J2 增强）。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, TypedDict

from kivi_agent.core.memory.backend import MemoryItem


# 单条记忆的 embedding 维度需在调用 embedding_fn 时保持一致；由 embedding_fn 实现保证。
EmbeddingFn = Callable[[str], list[float]]


# 去重结果：action=add 表示新增；merge 表示合并到 existing 中的某条；skip 表示重复。
class DedupResult(TypedDict):
    action: str  # "add" | "merge" | "skip"
    merged_with: str | None  # 当 action=merge 时指向被合并的 MemoryItem.id。
    score: float  # 触发的最高相似度（0.0-1.0）。
    reason: str  # 人类可读原因。


# 命中阈值常量。cosine > threshold 视为重复并合并；<= threshold 视为新条目。
DEFAULT_THRESHOLD: float = 0.95


# 计算两个等长向量的余弦相似度；任一向量为零向量时返回 0.0。
def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        # 维度不一致视为正交（0.0），不抛异常以保持调用者契约
        return 0.0
    if not a:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


@dataclass
class SemanticDeduplicator:
    """语义去重器：基于 cosine 相似度判断新记忆是否与已有记忆重复。"""

    embedding_fn: EmbeddingFn
    threshold: float = DEFAULT_THRESHOLD  # cosine 相似度阈值，> threshold 视为重复。

    # 对 new 与 existing 列表逐条计算 cosine 相似度。
    # 规则：任一 existing.score > threshold → merge（合并到最高分那条）；否则 → add。
    def deduplicate(
        self, new: MemoryItem, existing: list[MemoryItem]
    ) -> DedupResult:
        new_vec = self.embedding_fn(new.content)
        if not existing:
            return DedupResult(
                action="add",
                merged_with=None,
                score=0.0,
                reason="no existing memories",
            )

        best_match_id: str | None = None
        best_score = -1.0
        for item in existing:
            vec = self.embedding_fn(item.content)
            score = cosine_similarity(new_vec, vec)
            if score > best_score:
                best_score = score
                best_match_id = item.id

        # 严格 > threshold：合并到最高分那条
        if best_match_id is not None and best_score > self.threshold:
            return DedupResult(
                action="merge",
                merged_with=best_match_id,
                score=best_score,
                reason=f"cosine>{self.threshold} matches {best_match_id}",
            )

        return DedupResult(
            action="add",
            merged_with=None,
            score=best_score if best_score >= 0 else 0.0,
            reason=f"max cosine {best_score:.4f} <= threshold",
        )
