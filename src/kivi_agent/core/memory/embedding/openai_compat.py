"""OpenAICompatEmbedding：调用 OpenAI 兼容 /v1/embeddings（agent: package-vector-memory-v61）。

复用项目里 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY 思路（用户决定 2026-07-23）：
- 默认 base_url = ${OPENAI_BASE_URL}/v1/embeddings
- 兜底 base_url = ${ANTHROPIC_BASE_URL}/v1/embeddings
- 默认 key = ${OPENAI_API_KEY} → 兜底 ${ANTHROPIC_API_KEY}
- 默认 model = text-embedding-3-small（维度由模型决定，常见 1536）
"""

from __future__ import annotations

import os
from typing import Any

import httpx


# 把 OpenAI /v1/embeddings 响应解析为 list[list[float]]；异常结构抛错
def _parse_embeddings_response(payload: dict[str, Any]) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError(f"embeddings response missing 'data' list: {payload!r}")
    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"embeddings item not dict: {item!r}")
        emb = item.get("embedding")
        if not isinstance(emb, list):
            raise ValueError(f"embeddings item missing 'embedding' list: {item!r}")
        vectors.append([float(x) for x in emb])
    return vectors


# OpenAI 兼容 Embedding 客户端（httpx.AsyncClient，async 调用，无连接池泄漏）
class OpenAICompatEmbedding:
    # 初始化：base_url / api_key / model / dims；缺省值按用户决定的优先级链回退
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dims: int = 384,
        timeout_s: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # base_url 优先级：显式 > OPENAI_BASE_URL > ANTHROPIC_BASE_URL > 默认官方
        resolved_base = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
            or "https://api.openai.com"
        )
        self.base_url = resolved_base.rstrip("/")
        # api_key 优先级：显式 > OPENAI_API_KEY > ANTHROPIC_API_KEY
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or ""
        )
        self.model = model
        self.dims = dims
        self.timeout_s = timeout_s
        # 允许测试注入 client；未注入时延迟构造
        self._client: httpx.AsyncClient | None = client

    # 拿到 AsyncClient（未注入则按 timeout_s 构造一个）
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    # 关闭 client（注入的 client 不主动 close，由调用方负责）
    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # 实际 /v1/embeddings 调用；返回 list[list[float]]（顺序与输入一致）
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        url = f"{self.base_url}/v1/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {"model": self.model, "input": texts}
        # 维度参数（text-embedding-3-* 支持 dimensions；其它模型忽略也无害）
        if "text-embedding-3" in self.model:
            body["dimensions"] = self.dims
        resp = await client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return _parse_embeddings_response(resp.json())

    # 单条便捷方法（runtime_checkable 要求方法在类上显式存在）
    async def embed_one(self, text: str) -> list[float]:
        out = await self.embed([text])
        return out[0]


__all__ = ["OpenAICompatEmbedding"]
