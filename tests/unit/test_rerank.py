"""BM25Reranker 单测（agent: package-vector-memory-v61）。

覆盖：
- 简单分词器：英文整词 + 中文单字 + bigram
- bm25_rerank：基本排序 / 长度不匹配 / top_k 截断 / 空 query
- BM25Reranker：text_getter 注入 / 默认 identity
"""

from __future__ import annotations

import pytest

from kivi_agent.core.memory.rerank import BM25Reranker, bm25_rerank


# 功能：bm25_rerank 按相关性降序返回候选
# 设计：3 条候选 + 1 条 query，断言最相关候选排在第 1 位
def test_bm25_rerank_orders_by_relevance() -> None:
    candidates = ["doc about cats", "doc about dogs", "doc about programming languages"]
    texts = list(candidates)
    out = bm25_rerank("cats", candidates, texts, top_k=3)
    assert out[0] == "doc about cats"


# 功能：bm25_rerank top_k 截断生效
# 设计：5 条候选，top_k=2 断言返回 2 条
def test_bm25_rerank_top_k_truncates() -> None:
    candidates = [f"d{i}" for i in range(5)]
    out = bm25_rerank("d", candidates, list(candidates), top_k=2)
    assert len(out) == 2


# 功能：bm25_rerank 空 query 返回前 top_k 条（兜底）
# 设计：query="" 时仍要返回结果而非抛异常；这是"退化路径"约定
def test_bm25_rerank_empty_query_returns_top() -> None:
    candidates = ["a", "b", "c"]
    out = bm25_rerank("", candidates, list(candidates), top_k=2)
    assert out == ["a", "b"]


# 功能：bm25_rerank top_k<=0 返回空列表
# 设计：top_k=0 走 fast path
def test_bm25_rerank_zero_top_k_returns_empty() -> None:
    out = bm25_rerank("x", ["a", "b"], ["a", "b"], top_k=0)
    assert out == []


# 功能：bm25_rerank candidates 与 texts 长度不一致时抛 ValueError
# 设计：参数校验早失败，避免静默错位
def test_bm25_rerank_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        bm25_rerank("x", ["a"], ["a", "b"])


# 功能：bm25_rerank 中文 query 命中中文候选
# 设计：候选含"猫"和"狗"，query="猫" 断言"猫"排第一
def test_bm25_rerank_handles_chinese() -> None:
    candidates = ["关于猫的文档", "关于狗的文档", "其他内容"]
    out = bm25_rerank("猫", candidates, list(candidates), top_k=2)
    assert out[0] == "关于猫的文档"


# 功能：bm25_rerank 大小写不敏感
# 设计：query="PYTHON" 仍能命中候选 "python tutorial"
def test_bm25_rerank_case_insensitive() -> None:
    candidates = ["Python tutorial", "Java guide"]
    out = bm25_rerank("PYTHON", candidates, list(candidates), top_k=1)
    assert out == ["Python tutorial"]


# 功能：BM25Reranker 用 text_getter 从 dataclass 候选里提文本
# 设计：自定义对象 + getter，断言 rerank 用了对象字段而非 str(obj)
def test_bm25_reranker_uses_text_getter() -> None:
    from dataclasses import dataclass

    @dataclass
    class Doc:
        id: str
        title: str

    docs = [Doc(id="1", title="alpha"), Doc(id="2", title="beta")]
    reranker = BM25Reranker[Doc](text_getter=lambda d: d.title)
    out = reranker.rerank("alpha", docs, top_k=1)
    assert out[0].id == "1"


# 功能：BM25Reranker 默认 text_getter 把候选 str() 化
# 设计：text_getter=None 时 rerank 仍要工作（数字/字符串候选都 OK）
def test_bm25_reranker_default_text_getter() -> None:
    reranker: BM25Reranker[int] = BM25Reranker()
    out = reranker.rerank("42", [42, 0, 100], top_k=1)
    # 42 str() == "42" → 命中第一条
    assert out[0] == 42
