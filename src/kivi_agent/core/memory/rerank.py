"""BM25Reranker：简单版 TF-IDF + cosine 重排序（agent: package-vector-memory-v61）。

Wave 6.1 用 BM25 占位；Wave 8 升 Cross-Encoder。设计目标：
- 零依赖（不引入 rank_bm25 / jieba）
- 中文友好（按字符 bigram 切分，无需分词器）
- 纯函数 + 类型化（输入 candidates 不限类型，输出同序）
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# 中英文混合分词：英文按词切、中文按字符 bigram 切；单字过滤（噪声）
_TOKEN_RE = re.compile(r"[A-Za-z]+|[\u4e00-\u9fff]")


# 简单分词器：英文整词 / 中文单字 + 2-gram；不依赖 jieba 等外部包
def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    chars: list[str] = []
    for m in _TOKEN_RE.finditer(text.lower()):
        chunk = m.group(0)
        if "\u4e00" <= chunk[0] <= "\u9fff":
            chars.append(chunk)
        else:
            tokens.append(chunk)
    # 单字 + 连续 bigram（如 "你好世界" → "你好" "好世" "世界"）
    tokens.extend(chars)
    for i in range(len(chars) - 1):
        tokens.append(chars[i] + chars[i + 1])
    return tokens


# BM25 打分（k1=1.5, b=0.75 是 Lucene 默认；这里硬编码避免再传参）
def _bm25_score(
    query_tf: Counter[str],
    doc_tf: Counter[str],
    doc_len: int,
    avg_dl: float,
    idf: dict[str, float],
) -> float:
    k1 = 1.5
    b = 0.75
    score = 0.0
    for term, qf in query_tf.items():
        if term not in doc_tf:
            continue
        df_t = idf.get(term, 0.0)
        f_td = doc_tf[term]
        numerator = f_td * (k1 + 1)
        denominator = f_td + k1 * (1 - b + b * doc_len / max(avg_dl, 1.0))
        score += df_t * qf * (numerator / denominator)
    return score


# 把 query 文本与 candidates 文本做 BM25 重排序，按分数降序返回 top_k
def bm25_rerank[T](
    query: str,
    candidates: list[T],
    texts: list[str],
    top_k: int = 5,
) -> list[T]:
    """按 BM25(query, candidate_text) 降序返回 top_k 个候选（agent: package-vector-memory-v61）。

    参数：
    - `query`: 查询文本
    - `candidates`: 任意类型候选列表（与 texts 等长）
    - `texts`: 每个候选对应的文本（与 candidates 等长）；BM25 在 texts 上算
    - `top_k`: 返回前 k 个；k <= 0 时返回空
    """
    if top_k <= 0 or not candidates:
        return []
    if len(candidates) != len(texts):
        raise ValueError(
            f"candidates and texts length mismatch: {len(candidates)} vs {len(texts)}"
        )
    query_tokens = _tokenize(query)
    if not query_tokens:
        return candidates[:top_k]
    query_tf = Counter(query_tokens)

    # 文档侧分词
    docs_tokens: list[Counter[str]] = [Counter(_tokenize(t)) for t in texts]
    doc_lens = [max(sum(dt.values()), 1) for dt in docs_tokens]
    avg_dl = sum(doc_lens) / len(doc_lens) if doc_lens else 1.0

    # IDF：含 query 词的 doc 频率
    n_docs = len(candidates)
    idf: dict[str, float] = {}
    for term in query_tf:
        df = sum(1 for dt in docs_tokens if term in dt)
        # BM25+ 风格：df==0 时 idf=0（不算）；n_docs-df==0 时退化为 1e-6
        if df == 0:
            idf[term] = 0.0
        else:
            idf[term] = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))

    scored: list[tuple[float, T]] = []
    for cand, dt, dl in zip(candidates, docs_tokens, doc_lens):
        s = _bm25_score(query_tf, dt, dl, avg_dl, idf)
        scored.append((s, cand))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


# BM25Reranker 类：把 bm25_rerank 包装成 callable，方便注入 VectorMemoryBackend
class BM25Reranker[T]:
    """BM25 简单版重排序器（agent: package-vector-memory-v61）。

    构造时可指定 `text_getter` 从候选中提取文本字段（默认 identity）。
    """

    # 初始化：text_getter 用于从 T 提取 BM25 用文本（默认原样）
    def __init__(self, text_getter: Callable[[T], str] | None = None) -> None:
        self._text_getter: Callable[[T], str] = text_getter or (lambda x: str(x))

    # 调 bm25_rerank（构造时固定 text_getter）
    def rerank(self, query: str, candidates: list[T], top_k: int = 5) -> list[T]:
        texts = [self._text_getter(c) for c in candidates]
        return bm25_rerank(query, candidates, texts, top_k)


__all__ = ["BM25Reranker", "bm25_rerank"]
