"""web_search 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 冻结名 = web_search（v1 之前的 search_knowledge_base 已弃用）。
演示版 100% Mock：返回 3 条固定假数据，结构与 aigroup TavilyClient.search() 输出对齐
（id / title / url / snippet / source）。

未来切真 Tavily 只需替换 _mock_search() 实现 + 加 tavily-python 依赖；演示版与生产
保持 input_schema 完全一致。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.tools.base import ToolResult


# web_search 输入参数（agent: package-c-v1）
class WebSearchParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str  # 搜索关键词；演示版不做长度校验


# web_search 业务 Tool：演示版 Mock Tavily 搜索（agent: package-c-v1）
class WebSearchTool(BaseBusinessTool):
    """web_search Tool：返回 3 条固定假新闻。

    演示版不调 Tavily，不发任何外部 HTTP 请求。category="read" 因为无副作用。
    """

    params_model = WebSearchParams
    name = "web_search"
    category = "read"  # 无副作用
    description = (
        "Search the public web for the given query. "
        "Returns up to 3 web results with title, url, and snippet. "
        "Use this when the user's question requires fresh or external information "
        "that is not available in the local knowledge base. "
        "Each result has a stable id and a 'source' field set to 'mock-tavily' for traceability."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (natural language).",
            },
        },
        "required": ["query"],
    }

    # 演示版：返回 3 条固定假数据（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = WebSearchParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),  # noqa: E501
                is_error=True,
                error_type="schema_error",
            )
        results = _mock_web_search(p.query)
        # ToolResult.content 通常是字符串；这里 JSON 序列化便于 LLM 解析
        return ToolResult(content=json.dumps(results, ensure_ascii=False))


# 演示版 Mock 数据：3 条固定假新闻（agent: package-c-v1）
# 设计：返回结构与 aigroup TavilyClient.search() 对齐
def _mock_web_search(query: str) -> list[dict[str, Any]]:
    """返回 3 条固定假搜索结果，附带用户 query 便于 LLM 看到是 mock。

    数据选取原则：
    - 跨领域：技术 / 财经 / 时事 各 1 条，让 LLM 看到的是"真的在搜"而非单一领域
    - 时间新鲜：2025-2026 时间戳，匹配 C 报告"演示版 100% Mock"原则
    """
    return [
        {
            "id": "ws-001",
            "title": f"关于「{query}」的最新技术综述",
            "url": "https://example.com/news/2026/01/15/tech-overview",
            "snippet": (
                f"本文综述了 2026 年 1 月关于「{query}」的技术进展，"
                f"涵盖核心原理、最新论文与开源实现。"
            ),
            "source": "mock-tavily",
        },
        {
            "id": "ws-002",
            "title": f"{query} 行业应用案例分析",
            "url": "https://example.com/reports/2026/02/03/industry-case",
            "snippet": (
                f"三大头部企业（示例 A / B / C）在 2025 Q4 落地「{query}」方案的实践，"
                f"包含 ROI 数据与踩坑记录。"
            ),
            "source": "mock-tavily",
        },
        {
            "id": "ws-003",
            "title": f"FAQ: 常见关于「{query}」的疑问",
            "url": "https://example.com/faq/2026/03/10/common-questions",
            "snippet": (
                f"本文用问答形式整理了关于「{query}」最常被问到的 12 个问题，"
                f"包括入门门槛、典型误区、未来趋势。"
            ),
            "source": "mock-tavily",
        },
    ]
