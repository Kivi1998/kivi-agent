from __future__ import annotations

import math

import pytest

from kivi_agent.core.memory.backend import MemoryItem
from kivi_agent.core.memory.dedup import (
    DEFAULT_THRESHOLD,
    SemanticDeduplicator,
    cosine_similarity,
)


# 功能：cosine_similarity 完全相同向量返回 1.0
# 设计：单位向量自身点积 = 1.0
def test_cosine_similarity_identical_returns_one() -> None:
    v = [0.6, 0.8]
    assert math.isclose(cosine_similarity(v, v), 1.0, abs_tol=1e-9)


# 功能：cosine_similarity 正交向量返回 0.0
# 设计：dot = 0 → cosine = 0
def test_cosine_similarity_orthogonal_returns_zero() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert math.isclose(cosine_similarity(a, b), 0.0, abs_tol=1e-9)


# 功能：cosine_similarity 零向量返回 0.0
# 设计：norm 为 0 时不抛异常，返回 0 避免除零
def test_cosine_similarity_zero_vector_returns_zero() -> None:
    a = [0.0, 0.0]
    b = [1.0, 1.0]
    assert cosine_similarity(a, b) == 0.0


# 功能：cosine_similarity 维度不一致返回 0.0
# 设计：len(a) != len(b) 时直接 0.0 不抛
def test_cosine_similarity_dim_mismatch_returns_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


# 功能：cosine_similarity 空向量返回 0.0
# 设计：边界条件空输入
def test_cosine_similarity_empty_returns_zero() -> None:
    assert cosine_similarity([], []) == 0.0


# 功能：默认阈值是 0.95
# 设计：模块常量应与设计文档一致
def test_default_threshold_is_0_95() -> None:
    assert DEFAULT_THRESHOLD == 0.95


# 测试用 embedding 函数：把文本哈希映射到 4 维向量，便于构造已知 cosine 关系。
def _hash_embed(text: str) -> list[float]:
    h = abs(hash(text))
    # 构造 4 维：x1 = h%10, x2 = h%7, x3 = h%5, x4 = h%3，再除以最大可能值
    return [((h >> i) & 0xFF) / 255.0 for i in range(0, 32, 8)]


# 功能：空 existing 列表时直接返回 add
# 设计：边界条件，无已有记忆可对比
def test_dedup_with_empty_existing_returns_add() -> None:
    dedup = SemanticDeduplicator(embedding_fn=_hash_embed)
    new = MemoryItem(
        id="n", content="hello", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    result = dedup.deduplicate(new, [])
    assert result["action"] == "add"
    assert result["merged_with"] is None
    assert result["score"] == 0.0


# 功能：完全相同文本 cosine=1.0 > 0.95 应 merge
# 设计：自身 vs 自身 cosine=1.0 触发 merge
def test_dedup_identical_text_triggers_merge() -> None:
    dedup = SemanticDeduplicator(embedding_fn=_hash_embed)
    existing = [
        MemoryItem(
            id="e1", content="user prefers dark mode", memory_type="user",
            importance=0.7, status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    new = MemoryItem(
        id="n", content="user prefers dark mode", memory_type="user",
        importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
    )
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "merge"
    assert result["merged_with"] == "e1"
    assert result["score"] > 0.95


# 功能：正交文本 cosine≈0 → add
# 设计：完全无关的话题不应被合并
def test_dedup_orthogonal_text_triggers_add() -> None:
    dedup = SemanticDeduplicator(embedding_fn=_hash_embed)
    # 选择两个 hash 输出正交概率高的字符串
    existing = [
        MemoryItem(
            id="e1", content="alpha bravo charlie", memory_type="user",
            importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    new = MemoryItem(
        id="n", content="completely different text xyz qwerty",
        memory_type="user", importance=0.5, status="active",
        created_at="2026-01-01T00:00:00Z",
    )
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "add"
    assert result["score"] < 0.95


# 功能：阈值边界 0.95 严格大于才 merge
# 设计：构造一个 embedding_fn 使 score 恰好 = 0.95（threshold），断言不 merge
def test_dedup_threshold_boundary_exact_not_merged() -> None:
    # 构造两个 cosine 恰好等于 0.95 的向量
    a = [0.95, 0.3122]  # norm_a = sqrt(0.9025 + 0.0975) ≈ 1.0
    b = [1.0, 0.0]  # norm_b = 1.0
    # 校验首版构造的 cosine 接近 0.95
    assert math.isclose(cosine_similarity(a, b), 0.95, abs_tol=0.01)
    # 调整到精确 0.95：让 norm_a = 1
    a = [0.95, math.sqrt(1 - 0.95 ** 2)]
    b = [1.0, 0.0]
    assert math.isclose(cosine_similarity(a, b), 0.95, abs_tol=1e-9)

    def _fn(text: str) -> list[float]:
        return a if text == "new" else b

    dedup = SemanticDeduplicator(embedding_fn=_fn, threshold=0.95)
    new = MemoryItem(
        id="n", content="new", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    existing = [
        MemoryItem(
            id="e1", content="old", memory_type="user", importance=0.5,
            status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    result = dedup.deduplicate(new, existing)
    # 0.95 严格不 > 0.95，所以 add
    assert result["action"] == "add"
    assert result["score"] == pytest.approx(0.95, abs=1e-9)


# 功能：阈值边界 0.951 触发 merge
# 设计：稍高于阈值时走 merge 分支
def test_dedup_just_above_threshold_merges() -> None:
    a = [0.951, math.sqrt(1 - 0.951 ** 2)]
    b = [1.0, 0.0]

    def _fn(text: str) -> list[float]:
        return a if text == "new" else b

    dedup = SemanticDeduplicator(embedding_fn=_fn, threshold=0.95)
    new = MemoryItem(
        id="n", content="new", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    existing = [
        MemoryItem(
            id="e1", content="old", memory_type="user", importance=0.5,
            status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "merge"
    assert result["merged_with"] == "e1"
    assert result["score"] > 0.95


# 功能：多条 existing 时取最高分那条进行 merge
# 设计：3 条 existing（其中 1 条与 new 高度相关），断言 merged_with 指向最像的那条
def test_dedup_picks_highest_score_for_merge() -> None:
    # new 与 e2 相同（cosine=1.0），与 e1/e3 不相关
    def _fn(text: str) -> list[float]:
        if text == "new" or text == "same":
            return [1.0, 0.0]
        return [0.0, 1.0]  # 正交

    dedup = SemanticDeduplicator(embedding_fn=_fn)
    new = MemoryItem(
        id="n", content="new", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    existing = [
        MemoryItem(
            id="e1", content="different1", memory_type="user", importance=0.5,
            status="active", created_at="2026-01-01T00:00:00Z",
        ),
        MemoryItem(
            id="e2", content="same", memory_type="user", importance=0.5,
            status="active", created_at="2026-01-01T00:00:00Z",
        ),
        MemoryItem(
            id="e3", content="different3", memory_type="user", importance=0.5,
            status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "merge"
    assert result["merged_with"] == "e2"


# 功能：跨 memory_type 也走相同去重规则
# 设计：existing 是 project 类型，new 是 user 类型，但内容相同 → 仍然 merge
def test_dedup_across_memory_types() -> None:
    dedup = SemanticDeduplicator(embedding_fn=_hash_embed)
    existing = [
        MemoryItem(
            id="e1", content="shared content", memory_type="project",
            importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    new = MemoryItem(
        id="n", content="shared content", memory_type="user",
        importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
    )
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "merge"


# 功能：跨 session（不同 created_at）也参与对比
# 设计：created_at 不影响去重，跨时间写入相同内容仍会 merge
def test_dedup_across_sessions() -> None:
    dedup = SemanticDeduplicator(embedding_fn=_hash_embed)
    existing = [
        MemoryItem(
            id="e1", content="user prefers dark mode", memory_type="user",
            importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
        ),
    ]
    new = MemoryItem(
        id="n", content="user prefers dark mode", memory_type="user",
        importance=0.5, status="active", created_at="2026-12-31T23:59:59Z",
    )
    result = dedup.deduplicate(new, existing)
    assert result["action"] == "merge"
    assert result["merged_with"] == "e1"


# 功能：可注入 embedding_fn
# 设计：传入自定义函数，断言函数被调用
def test_dedup_injects_embedding_fn() -> None:
    calls: list[str] = []

    def _fn(text: str) -> list[float]:
        calls.append(text)
        return [1.0, 0.0] if text == "a" else [0.0, 1.0]

    dedup = SemanticDeduplicator(embedding_fn=_fn)
    new = MemoryItem(
        id="n", content="a", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    dedup.deduplicate(new, [])
    assert "a" in calls
