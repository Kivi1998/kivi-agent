"""OpenAICompatEmbedding 单测（Wave 8.2 / agent: real-llm-e2e）。

覆盖：
- 批处理：batch_size=2 时把 5 条文本切成 3 批（2/2/1）
- 重试：429 → 200 重试 1 次成功
- 重试：500 耗尽抛 HTTPStatusError
- 超时：httpx.TimeoutException 归一重试
- 顺序保持：批切分后输出顺序与输入一致
- 已有契约：dims / model / base_url / api_key 优先级（基线）
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from kivi_agent.core.memory.embedding.openai_compat import OpenAICompatEmbedding


# 构造一个 _json_response 用于 mock transport
def _json_response(status: int = 200, payload: dict[str, Any] | None = None) -> httpx.Response:
    if payload is None:
        payload = {}
    return httpx.Response(
        status_code=status, json=payload, request=httpx.Request("POST", "https://fake")
    )


# 构造一组 embeddings payload（n 条）
def _emb_payload(n: int) -> dict[str, Any]:
    return {"data": [{"embedding": [float(i), float(i) + 0.1]} for i in range(n)]}


# 构造一个 mock provider（用 transport，避免 monkeypatch）
def _make_provider(
    responses: list[httpx.Response | Exception],
    *,
    model: str = "text-embedding-3-small",
    dims: int = 2,
    max_retries: int = 3,
    batch_size: int = 100,
    timeout_s: float = 30.0,
) -> tuple[OpenAICompatEmbedding, _MockTransport]:
    transport = _MockTransport(responses)
    client = httpx.AsyncClient(transport=transport, timeout=timeout_s)
    emb = OpenAICompatEmbedding(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        model=model,
        dims=dims,
        max_retries=max_retries,
        batch_size=batch_size,
        timeout_s=timeout_s,
        client=client,
    )
    return emb, transport


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if not self._responses:
            raise AssertionError("no more mock responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# ========== 基础契约 ==========
# 功能：embed() 单条输入返回 1 个向量，维度与 dims 一致
# 设计：传 1 条文本，mock 返回 [{emb: [...]}]
@pytest.mark.asyncio
async def test_embed_single_text_returns_one_vector() -> None:
    emb, _ = _make_provider([_json_response(200, _emb_payload(1))])
    out = await emb.embed(["hello"])
    assert len(out) == 1
    assert len(out[0]) == 2


# 功能：embed_one() 等价于 embed(["text"])[0]
# 设计：传 "hi"，断言返回 1 个向量
@pytest.mark.asyncio
async def test_embed_one_returns_single_vector() -> None:
    emb, _ = _make_provider([_json_response(200, _emb_payload(1))])
    v = await emb.embed_one("hi")
    assert len(v) == 2


# 功能：embed([]) 不发任何 HTTP 请求
# 设计：传空列表，断言 transport.calls 为空
@pytest.mark.asyncio
async def test_embed_empty_input_skips_request() -> None:
    emb, transport = _make_provider([])
    out = await emb.embed([])
    assert out == []
    assert len(transport.calls) == 0


# ========== 批处理 ==========
# 功能：batch_size=2 把 5 条文本切成 3 批（2/2/1）
# 设计：构造 3 个 _emb_payload(2), _emb_payload(2), _emb_payload(1) 响应，断言 3 次 HTTP 调用且每批 input 数量正确
@pytest.mark.asyncio
async def test_embed_batches_input_by_batch_size() -> None:
    responses = [
        _json_response(200, _emb_payload(2)),
        _json_response(200, _emb_payload(2)),
        _json_response(200, _emb_payload(1)),
    ]
    emb, transport = _make_provider(responses, batch_size=2)
    out = await emb.embed(["a", "b", "c", "d", "e"])
    assert len(out) == 5
    # 3 次请求：2/2/1
    assert len(transport.calls) == 3
    import json

    sizes = [json.loads(c.content).get("input", []) and len(json.loads(c.content)["input"]) for c in transport.calls]
    assert sizes == [2, 2, 1]


# 功能：批切分后输出顺序与输入顺序一致
# 设计：5 条文本 batch_size=2，断言返回 5 个向量且每个的内部值可区分
@pytest.mark.asyncio
async def test_embed_preserves_input_order_across_batches() -> None:
    # 每个响应里返回带不同值的向量（i*10）便于区分
    def payload(start: int, n: int) -> dict[str, Any]:
        return {"data": [{"embedding": [float(start + i), 0.0]} for i in range(n)]}

    responses = [_json_response(200, payload(0, 2)), _json_response(200, payload(2, 2)), _json_response(200, payload(4, 1))]
    emb, _ = _make_provider(responses, batch_size=2)
    out = await emb.embed(["a", "b", "c", "d", "e"])
    assert out[0][0] == 0.0
    assert out[1][0] == 1.0
    assert out[2][0] == 2.0
    assert out[3][0] == 3.0
    assert out[4][0] == 4.0


# 功能：batch_size 大于等于输入大小时走单批快速路径
# 设计：3 条文本 + batch_size=10，断言只发 1 次 HTTP 请求
@pytest.mark.asyncio
async def test_embed_single_batch_when_under_batch_size() -> None:
    emb, transport = _make_provider([_json_response(200, _emb_payload(3))], batch_size=10)
    out = await emb.embed(["a", "b", "c"])
    assert len(out) == 3
    assert len(transport.calls) == 1


# ========== 重试 ==========
# 功能：429 后第二次成功
# 设计：mock 429 + 200，断言重试 1 次后成功且 2 次 HTTP 调用
@pytest.mark.asyncio
async def test_embed_retries_on_429_then_succeeds() -> None:
    responses = [
        httpx.Response(status_code=429, text="rate", request=httpx.Request("POST", "https://fake")),
        _json_response(200, _emb_payload(1)),
    ]
    emb, transport = _make_provider(responses, max_retries=3)
    out = await emb.embed(["hi"])
    assert len(out) == 1
    assert len(transport.calls) == 2


# 功能：500 耗尽 max_retries 后抛 HTTPStatusError
# 设计：max_retries=2 + 3 个 500，断言抛错且 3 次 HTTP 调用
@pytest.mark.asyncio
async def test_embed_exhausts_retries_on_500() -> None:
    responses = [
        httpx.Response(status_code=500, text="x", request=httpx.Request("POST", "https://fake")),
        httpx.Response(status_code=500, text="x", request=httpx.Request("POST", "https://fake")),
        httpx.Response(status_code=500, text="x", request=httpx.Request("POST", "https://fake")),
    ]
    emb, transport = _make_provider(responses, max_retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        await emb.embed(["x"])
    # 1 + 2 retries = 3 total
    assert len(transport.calls) == 3


# 功能：503 同样触发重试
# 设计：mock 503 + 200，断言重试 1 次后成功
@pytest.mark.asyncio
async def test_embed_retries_on_503_then_succeeds() -> None:
    responses = [
        httpx.Response(status_code=503, text="x", request=httpx.Request("POST", "https://fake")),
        _json_response(200, _emb_payload(1)),
    ]
    emb, transport = _make_provider(responses, max_retries=3)
    out = await emb.embed(["x"])
    assert len(out) == 1


# 功能：ConnectError 触发重试
# 设计：mock ConnectError + 200，断言重试 1 次后成功
@pytest.mark.asyncio
async def test_embed_retries_on_connect_error() -> None:
    emb, transport = _make_provider(
        [httpx.ConnectError("refused"), _json_response(200, _emb_payload(1))],
        max_retries=3,
    )
    out = await emb.embed(["x"])
    assert len(out) == 1
    assert len(transport.calls) == 2


# 功能：400 不会触发重试（非 429/5xx 立即抛 HTTPStatusError）
# 设计：mock 400，断言 1 次调用后抛错
@pytest.mark.asyncio
async def test_embed_no_retry_on_400() -> None:
    responses = [httpx.Response(status_code=400, text="bad", request=httpx.Request("POST", "https://fake"))]
    emb, transport = _make_provider(responses, max_retries=3)
    with pytest.raises(httpx.HTTPStatusError):
        await emb.embed(["x"])
    assert len(transport.calls) == 1


# ========== 超时 ==========
# 功能：httpx.TimeoutException 触发重试，最终成功
# 设计：mock TimeoutException + 200，断言重试 1 次后成功
@pytest.mark.asyncio
async def test_embed_retries_on_timeout() -> None:
    emb, transport = _make_provider(
        [httpx.ConnectTimeout("slow"), _json_response(200, _emb_payload(1))],
        max_retries=3,
    )
    out = await emb.embed(["x"])
    assert len(out) == 1
    assert len(transport.calls) == 2


# 功能：连续超时耗尽 max_retries 后抛错
# 设计：max_retries=1 + 2 个 ConnectTimeout，断言抛错且 2 次调用
@pytest.mark.asyncio
async def test_embed_exhausts_retries_on_timeout() -> None:
    emb, transport = _make_provider(
        [httpx.ConnectTimeout("slow"), httpx.ConnectTimeout("slow")], max_retries=1
    )
    with pytest.raises(httpx.ConnectTimeout):
        await emb.embed(["x"])
    assert len(transport.calls) == 2


# ========== 已有契约（基线） ==========
# 功能：base_url / api_key 优先级仍按 env 链回退（与 Wave 6.1 一致）
# 设计：monkeypatch 设 OPENAI_BASE_URL 优先级 > 默认
def test_base_url_priority_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.com")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    emb = OpenAICompatEmbedding(api_key="k")
    assert emb.base_url == "https://proxy.example.com"


# 功能：构造时 timeout_s / timeout 别名一致
# 设计：构造 timeout_s=15，断言 emb.timeout == 15（兼容旧 / 新调用）
def test_timeout_alias_compatible() -> None:
    emb = OpenAICompatEmbedding(api_key="k", base_url="https://x", timeout_s=15.0)
    assert emb.timeout_s == 15.0
    assert emb.timeout == 15.0


# 功能：max_retries=0 关闭重试（不抛错，但 429 直接抛 HTTPStatusError）
# 设计：max_retries=0 + 429 响应，断言 1 次调用后抛错（不重试）
@pytest.mark.asyncio
async def test_zero_retries_disables_retry() -> None:
    responses = [httpx.Response(status_code=429, text="x", request=httpx.Request("POST", "https://fake"))]
    emb, transport = _make_provider(responses, max_retries=0)
    with pytest.raises(httpx.HTTPStatusError):
        await emb.embed(["x"])
    assert len(transport.calls) == 1
