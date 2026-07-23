"""RAG 数据类型（agent: package-rag-real-v4）。

按 v1 §1 rag_query Tool 内部字段：sources / score / url 等。
从 Pydantic 推导 + 与 v1 contracts 对齐。

设计要点：
- RagSource 与 RagSourcesCitedEvent.sources[].item 字段对齐（id / title / snippet / score / url）
- RagSearchResult 是 RagKbClient.search() 的返回类型；含 answer / sources / rewritten_query
- score 用 Pydantic Field 约束 0.0-1.0（演示版 Mock 也遵守）
- url 字段允许 None；提供时必须是 http(s) 协议（最小防御，禁止 file:// 等本地协议）
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# 单条知识片段（与 RagSourcesCitedEvent.sources[].item 对齐）
class RagSource(BaseModel):
    id: str
    title: str
    snippet: str
    score: float = Field(ge=0.0, le=1.0)
    url: str | None = None

    # 校验 url 必须以 http(s) 协议开头（最小防御，禁止 file:// 等本地协议）
    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"url must start with http:// or https://, got: {v!r}")
        return v


# RAG 检索结果
class RagSearchResult(BaseModel):
    answer: str
    sources: list[RagSource]
    rewritten_query: str  # rag_query 内部步骤：query rewrite 后的查询
