"""OpenAICompatEmbedding：调用 OpenAI 兼容 /v1/embeddings（agent: package-vector-memory-v61）。

复用项目里 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY 思路（用户决定 2026-07-23）：
- 默认 base_url = ${OPENAI_BASE_URL}/v1/embeddings
- 兜底 base_url = ${ANTHROPIC_BASE_URL}/v1/embeddings
- 默认 key = ${OPENAI_API_KEY} → 兜底 ${ANTHROPIC_API_KEY}
- 默认 model = text-embedding-3-small（维度由模型决定，常见 1536）

Wave 8.2 增强（agent: real-llm-e2e）：
- 新增 `max_retries`（默认 3）与 `batch_size`（默认 100）
- `embed()` 内部按 `batch_size` 分批；每批重试 + 超时归一
- `timeout_s` 别名 `timeout`（兼容旧调用）
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

# 触发重试的 HTTP 状态码
_RETRY_STATUSES = frozenset({429, 500, 503, 504})
# 指数退避：1s / 2s / 4s / 8s（截顶避免 sleep 太久）
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


# 解析 OpenAI /v1/embeddings 响应；异常结构抛错
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


# 截顶退避秒数（避免 sleep 太久）
def _backoff(attempt: int) -> float:
    if attempt < 0:
        attempt = 0
    return _RETRY_BACKOFF_S[min(attempt, len(_RETRY_BACKOFF_S) - 1)]


class OpenAICompatEmbedding:
    # 初始化：base_url / api_key / model / dims / timeout_s / max_retries / batch_size；client 注入
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dims: int = 384,
        timeout_s: float = 30.0,
        max_retries: int = 3,
        batch_size: int = 100,
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
        # 兼容别名：timeout == timeout_s
        self.timeout = timeout_s
        self.max_retries = max(0, max_retries)
        # 单批最大文本数（OpenAI 限制 2048，但保守 100 避免超长输入）
        self.batch_size = max(1, batch_size)
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

    # 单批 /v1/embeddings 调用 + 重试 + 错误归一
    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        if not batch:
            return []
        client = self._get_client()
        url = f"{self.base_url}/v1/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict[str, Any] = {"model": self.model, "input": batch}
        # 维度参数（text-embedding-3-* 支持 dimensions；其它模型忽略也无害）
        if "text-embedding-3" in self.model:
            body["dimensions"] = self.dims

        total_attempts = self.max_retries + 1
        last_err: Exception | None = None
        for attempt in range(total_attempts):
            try:
                resp = await client.post(url, json=body, headers=headers)
            except (TimeoutError, httpx.TimeoutException) as exc:
                last_err = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(_backoff(attempt))
                continue
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as exc:
                last_err = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(_backoff(attempt))
                continue

            if resp.status_code in _RETRY_STATUSES:
                last_err = httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
                if attempt >= self.max_retries:
                    # 用 raise_for_status 抛 HTTPStatusError
                    resp.raise_for_status()
                await asyncio.sleep(_backoff(attempt))
                continue

            # 非重试状态码 —— 抛给上层处理
            resp.raise_for_status()
            return _parse_embeddings_response(resp.json())

        # 防御性：理论不可达
        if last_err is not None:
            raise last_err
        n = len(batch)
        retries = self.max_retries
        raise RuntimeError(f"embedding exhausted {retries} retries for batch of {n}")

    # 实际 /v1/embeddings 调用；返回 list[list[float]]（顺序与输入一致）
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """按 batch_size 分批调用 OpenAI 兼容 /v1/embeddings；返回顺序与输入一致。"""
        if not texts:
            return []
        # 全部文本一次性放得下则走单批快速路径
        if len(texts) <= self.batch_size:
            return await self._embed_batch(texts)
        # 多批：按 batch_size 切片，串行调用（保持顺序；如需并发可由调用方包）
        results: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start : start + self.batch_size]
            vectors = await self._embed_batch(chunk)
            results.extend(vectors)
        return results

    # 单条便捷方法（runtime_checkable 要求方法在类上显式存在）
    async def embed_one(self, text: str) -> list[float]:
        out = await self.embed([text])
        return out[0]


__all__ = ["OpenAICompatEmbedding"]
