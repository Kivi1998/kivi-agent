"""rag_query 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 决议：rag_query 单一 Tool 内部完成 rewrite + retrieval。
旧名 rag_query_rewrite（独立 Tool）已弃用——C 报告 §3.3 + §3.4 明确指出
rewrite 是 rag_query 的内部步骤，不能注册成独立 Tool。

演示版 100% Mock：
- 内部步骤：rewritten_query = query + " [refined]"（演示版简化）
- 返回：answer + sources + rewritten_query
- sources 至少 2 条 mock
- 引用格式：<ref_json>{...}</ref_json> 收尾（按 C 报告 §3.6 复用 aigroup 格式）

未来切真 RAGFlow：替换 _mock_retrieval() + _format_citation() 实现。
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.tools.base import ToolResult


# rag_query 输入参数（agent: package-c-v1）
class RagQueryParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str  # 用户原始问题
    knowledge_base_id: str | None = None  # 可选：按 v1 §2 字段名


# rag_query 单条知识片段（演示版 Mock 数据结构，对齐 C 报告 §3.2 Source 字段）
class MockSource(BaseModel):
    id: str
    title: str
    snippet: str
    score: float  # 0-1，越高越相关
    url: str | None = None


# rag_query 业务 Tool：演示版 Mock RAG 检索（agent: package-c-v1）
class RagQueryTool(BaseBusinessTool):
    """rag_query Tool：内部完成 rewrite + retrieval。

    按 v1 §1 规则，rag_query_rewrite 不暴露为独立 Tool——它只是本 Tool 的内部步骤。
    演示版不调 RAGFlow，不发任何外部 HTTP 请求。category="read" 因为无副作用。
    """

    params_model = RagQueryParams
    name = "rag_query"
    category = "read"  # 无副作用
    description = (
        "Query a knowledge base with the given question. Internally performs "
        "query rewriting and retrieval in a single call, then returns the answer "
        "with cited sources. The output ends with a <ref_json>{...}</ref_json> block "
        "containing structured source metadata for downstream rendering. "
        "Use this when the user's question can be answered from a curated knowledge base."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The user's question in natural language.",
            },
            "knowledge_base_id": {
                "type": "string",
                "description": (
                    "Optional knowledge base identifier. If omitted, the default "
                    "knowledge base configured in RunContext is used."
                ),
            },
        },
        "required": ["query"],
    }

    # 演示版入口：参数校验 → rewrite → retrieval → 格式化（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = RagQueryParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),
                is_error=True,
                error_type="schema_error",
            )
        # 内部步骤 1：query rewrite（演示版简化，真实实现是 LLM 调用）
        rewritten_query = _mock_query_rewrite(p.query, p.knowledge_base_id)
        # 内部步骤 2：retrieval（演示版返回固定 2 条知识片段）
        sources = _mock_retrieval(rewritten_query, p.knowledge_base_id)
        # 内部步骤 3：format citation（按 C 报告 §3.6 aigroup 格式）
        answer_text, ref_json = _format_citation(rewritten_query, sources)
        return ToolResult(
            content=json.dumps(
                {
                    "answer": answer_text,
                    "sources": [s.model_dump() for s in sources],
                    "rewritten_query": rewritten_query,
                    "ref_json": ref_json,
                },
                ensure_ascii=False,
            )
        )


# 演示版 query rewrite（agent: package-c-v1）
# 真实实现：调 LLM 改写对话式 query 为独立可检索 query（aigroup rag_query_rewrite_service.py 191 行）
def _mock_query_rewrite(query: str, knowledge_base_id: str | None) -> str:
    """演示版 query rewrite：原 query + " [refined]"。

    真实实现会调 LLM（aigroup 用 256 tokens 限制、15s 超时、6 条历史窗口、失败回退原 query）。
    演示版简化到一行后缀。
    """
    suffix = f" @kb[{knowledge_base_id}]" if knowledge_base_id else ""
    return f"{query} [refined]{suffix}"


# 演示版 retrieval（agent: package-c-v1）
# 真实实现：调 RAGFlow /retrievalSimple，top_k + score_threshold + vector_similarity_weight
def _mock_retrieval(rewritten_query: str, knowledge_base_id: str | None) -> list[MockSource]:
    """演示版 retrieval：返回 2 条固定知识片段。

    选取原则：
    - 跨主题：技术文档 + 行业报告 各 1 条，覆盖常见 RAG 场景
    - 字段齐全：id / title / snippet / score（0-1）/ url（按 C 报告 §3.2）
    - score 设高（0.92-0.95）让 LLM 看着是"高置信" mock
    """
    kb_label = knowledge_base_id or "default"
    return [
        MockSource(
            id=f"kb-{kb_label}-001",
            title="RAG 系统架构综述",
            snippet=(
                f"本白皮书介绍检索增强生成（RAG）系统的标准架构，包含 query rewrite、"
                f"embedding、向量检索、rerank、answer generation 五大模块。"
                f"针对查询「{rewritten_query}」，推荐使用 hybrid retrieval + bge-reranker。"
            ),
            score=0.95,
            url=f"https://kb.example.com/{kb_label}/whitepaper/rag-architecture",
        ),
        MockSource(
            id=f"kb-{kb_label}-002",
            title="企业内部知识库最佳实践",
            snippet=(
                f"本文总结 2025-2026 年企业内部知识库建设的 8 条最佳实践，"
                f"包括知识切片策略、权限隔离、审计追踪、敏感信息过滤等。"
                f"对查询「{rewritten_query}」尤其推荐按部门 + 角色双维度权限控制。"
            ),
            score=0.92,
            url=f"https://kb.example.com/{kb_label}/guides/internal-kb-best-practices",
        ),
    ]


# 演示版引用格式化（agent: package-c-v1）
# 复用 C 报告 §3.6 aigroup format_knowledge_chunks 格式：
# <知识片段 [i] id=... title="..." score=... url="...">content</知识片段>
# 末尾追加 <ref_json>{...}</ref_json>
def _format_citation(rewritten_query: str, sources: list[MockSource]) -> tuple[str, str]:
    """返回 (answer_text, ref_json) 元组。

    answer_text：含 <知识片段> XML 格式 + 末尾 <ref_json> 标签
    ref_json：纯 JSON 字符串（供前端解析）
    """
    chunks_xml: list[str] = []
    for i, src in enumerate(sources, start=1):
        url_attr = f' url="{src.url}"' if src.url else ""
        chunks_xml.append(
            f'<知识片段 [{i}] id="{src.id}" title="{src.title}" score="{src.score}"{url_attr}>'
            f'{src.snippet}</知识片段>'
        )
    ref_payload = {
        "query": rewritten_query,
        "sources": [s.model_dump() for s in sources],
        "version": 1,
    }
    ref_json_str = json.dumps(ref_payload, ensure_ascii=False)
    answer_text = (
        f"Mock RAG answer for: {rewritten_query}\n\n"
        + "\n\n".join(chunks_xml)
        + f"\n\n<ref_json>{ref_json_str}</ref_json>"
    )
    return answer_text, ref_json_str
