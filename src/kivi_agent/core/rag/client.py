"""RAG HTTP 客户端（agent: package-rag-real-v4）。

调用本地 rag-kb API（默认 http://localhost:8001）：
- POST /api/v1/search     — 检索
- GET  /health             — 健康检查
- GET  /api/v1/version     — 版本（可选）

rag-kb 不在本仓库；本客户端按 REST 惯例设计 request/response schema，
假设如下（待用户/rag-kb 维护方 review）：
- POST /api/v1/search
  请求：{"query": str, "kb_id": str | null, "top_k": int = 5}
  响应：{"answer", "sources": [...], "rewritten_query": str}

设计要点：
- 使用 httpx.AsyncClient（已有依赖，无需新增）
- _ensure_client 懒初始化：避免导入时建连；close() 后可重新使用
- search() 失败统一包成 RagKbError（超时 / 4xx / 5xx / schema 不匹配）
- health_check() 不抛错：仅返回 bool（健康检查调用方需要"软失败"语义）
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from kivi_agent.core.rag.types import RagSearchResult, RagSource

log = logging.getLogger(__name__)


# RAG HTTP 异常
class RagKbError(Exception):
    """rag-kb 调用失败（超时 / 4xx / 5xx / schema 不匹配）。"""


class RagKbClient:
    """异步 RAG HTTP 客户端（agent: package-rag-real-v4）。"""

    DEFAULT_TIMEOUT_S = 5.0
    DEFAULT_TOP_K = 5
    SEARCH_PATH = "/api/v1/search"
    HEALTH_PATH = "/health"

    # 初始化客户端；连接懒加载（首次 search / health_check 时建立）
    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        timeout_s: float = DEFAULT_TIMEOUT_S,
        *,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        # 测试用：传入 httpx.MockTransport 替换真实网络；生产路径不传
        self._transport = _transport
        self._client: httpx.AsyncClient | None = None

    # 懒加载 httpx 客户端（首次调用时建立）
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            kwargs: dict[str, object] = {"timeout": self._timeout_s}
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._client = httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]
        return self._client

    # 调 POST /api/v1/search，返回 RagSearchResult
    async def search(
        self,
        query: str,
        kb_id: str | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> RagSearchResult:
        client = await self._ensure_client()
        try:
            resp = await client.post(
                f"{self._base_url}{self.SEARCH_PATH}",
                json={"query": query, "kb_id": kb_id, "top_k": top_k},
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise RagKbError(f"rag-kb search failed: {e}") from e
        try:
            data: dict[str, Any] = resp.json()
            return RagSearchResult(
                answer=data["answer"],
                rewritten_query=data.get("rewritten_query", query),
                sources=[RagSource(**s) for s in data.get("sources", [])],
            )
        except (KeyError, ValueError, TypeError) as e:
            raise RagKbError(f"rag-kb response schema mismatch: {e}") from e

    # 调 GET /health，返回 True=健康 False=不健康（不抛错）
    async def health_check(self) -> bool:
        client = await self._ensure_client()
        try:
            resp = await client.get(f"{self._base_url}{self.HEALTH_PATH}")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # 关闭底层 httpx 客户端并复位
    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
