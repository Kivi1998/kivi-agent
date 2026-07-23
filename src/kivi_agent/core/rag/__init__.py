"""RAG 检索子包（agent: package-rag-real-v4）。

按 WT-F1 任务书：
- types.py：RagSource / RagSearchResult 数据模型（与 v1 §1 rag_query Tool 内部字段对齐）
- client.py：RagKbClient 异步 HTTP 客户端（httpx 封装）+ search / health_check / close

本包仅定义"kivi-agent → rag-kb"的契约；rag-kb 服务本身在外部仓库，不在本仓维护。
"""

from kivi_agent.core.rag.client import RagKbClient, RagKbError
from kivi_agent.core.rag.types import RagSearchResult, RagSource

__all__ = [
    "RagKbClient",
    "RagKbError",
    "RagSearchResult",
    "RagSource",
]
