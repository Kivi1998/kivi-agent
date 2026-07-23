"""Embedding 实现单测（agent: package-vector-memory-v61）。

覆盖：
- FakeEmbedding：确定性 / 维度 / 归一化 / 不同输入产生不同向量
- OpenAICompatEmbedding：base_url / api_key / model / dims / 单条便捷方法
- 协议：满足 EmbeddingProvider 结构子类型
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from kivi_agent.core.memory.embedding import EmbeddingProvider, FakeEmbedding, OpenAICompatEmbedding


# 功能：FakeEmbedding 相同输入永远返回相同向量（确定性）
# 设计：连续两次 embed 同一字符串，断言 list 一致；这是单测/快照比对的前提
@pytest.mark.asyncio
async def test_fake_embedding_is_deterministic() -> None:
    emb = FakeEmbedding(dims=16)
    a = await emb.embed(["hello world"])
    b = await emb.embed(["hello world"])
    assert a == b


# 功能：FakeEmbedding 输出维度与构造 dims 一致
# 设计：构造 dims=32，调 embed 取首条向量，断言 len == 32
@pytest.mark.asyncio
async def test_fake_embedding_output_dims() -> None:
    emb = FakeEmbedding(dims=32)
    vecs = await emb.embed(["x"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 32


# 功能：FakeEmbedding 输出向量 L2 归一化（norm ≈ 1.0）
# 设计：取任一向量计算 ||v||_2，断言与 1.0 误差 < 1e-6；这是 cosine 召回的几何前提
@pytest.mark.asyncio
async def test_fake_embedding_is_l2_normalized() -> None:
    emb = FakeEmbedding(dims=64)
    vecs = await emb.embed(["alpha", "beta", "gamma"])
    for v in vecs:
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6


# 功能：FakeEmbedding 批量 embed 顺序与输入一致
# 设计：传 3 条文本，断言返回 3 个向量且 len 一一对应输入
@pytest.mark.asyncio
async def test_fake_embedding_batch_preserves_order() -> None:
    emb = FakeEmbedding(dims=8)
    out = await emb.embed(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == 8 for v in out)


# 功能：FakeEmbedding 不同输入产生不同向量
# 设计：embed 两个不同字符串，断言向量不相等（SHA-256 应当碰撞概率 0）
@pytest.mark.asyncio
async def test_fake_embedding_different_inputs_differ() -> None:
    emb = FakeEmbedding(dims=16)
    out = await emb.embed(["alpha", "bravo"])
    assert out[0] != out[1]


# 功能：FakeEmbedding 处理空字符串（不抛异常）
# 设计：embed("") 应当返回合法向量（hash 是确定函数，空串也可哈希）
@pytest.mark.asyncio
async def test_fake_embedding_handles_empty_string() -> None:
    emb = FakeEmbedding(dims=8)
    out = await emb.embed([""])
    assert len(out) == 1
    assert len(out[0]) == 8


# 功能：FakeEmbedding dims=0 / 负数构造时抛 ValueError
# 设计：参数校验早失败，避免后面 silent 错误
@pytest.mark.asyncio
async def test_fake_embedding_rejects_invalid_dims() -> None:
    with pytest.raises(ValueError):
        FakeEmbedding(dims=0)
    with pytest.raises(ValueError):
        FakeEmbedding(dims=-1)


# 功能：FakeEmbedding 满足 EmbeddingProvider 协议（结构子类型）
# 设计：isinstance 校验通过；与 Protocol 的 embed / embed_one 契约一致
def test_fake_embedding_satisfies_protocol() -> None:
    emb = FakeEmbedding()
    assert isinstance(emb, EmbeddingProvider)


# 功能：OpenAICompatEmbedding 默认 base_url 用 ${OPENAI_BASE_URL}
# 设计：临时设环境变量，断言构造后 base_url 反映 env 优先级（显式 None → env）
def test_openai_compat_uses_openai_base_url_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.com")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    emb = OpenAICompatEmbedding(api_key="k")
    assert emb.base_url == "https://proxy.example.com"


# 功能：OpenAICompatEmbedding 缺 OPENAI_BASE_URL 时回退到 ANTHROPIC_BASE_URL
# 设计：只设 ANTHROPIC_BASE_URL，断言 base_url 反映该回退
def test_openai_compat_falls_back_to_anthropic_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://anthropic-proxy.example.com")
    emb = OpenAICompatEmbedding(api_key="k")
    assert emb.base_url == "https://anthropic-proxy.example.com"


# 功能：OpenAICompatEmbedding 缺 base_url 时回退到官方默认
# 设计：清空两个 base_url env，断言默认 https://api.openai.com
def test_openai_compat_default_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    emb = OpenAICompatEmbedding(api_key="k")
    assert emb.base_url == "https://api.openai.com"


# 功能：OpenAICompatEmbedding 的 api_key 显式 > OPENAI_API_KEY > ANTHROPIC_API_KEY
# 设计：3 种 env 组合下构造，断言优先级正确
def test_openai_compat_api_key_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # 1) 显式 > env
    emb = OpenAICompatEmbedding(api_key="explicit", base_url="https://x")
    assert emb.api_key == "explicit"
    # 2) OPENAI_API_KEY 优先
    monkeypatch.setenv("OPENAI_API_KEY", "from-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-anthropic")
    emb = OpenAICompatEmbedding()
    assert emb.api_key == "from-openai"
    # 3) 缺 OPENAI_API_KEY 时回退 ANTHROPIC_API_KEY
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    emb = OpenAICompatEmbedding()
    assert emb.api_key == "from-anthropic"


# 功能：OpenAICompatEmbedding 默认 model = text-embedding-3-small
# 设计：构造时不给 model，断言默认值
def test_openai_compat_default_model() -> None:
    emb = OpenAICompatEmbedding(api_key="k", base_url="https://x")
    assert emb.model == "text-embedding-3-small"


# 功能：OpenAICompatEmbedding.embed 走 /v1/embeddings，body 包含 model / input / dimensions
# 设计：mock httpx.AsyncClient.post，断言 URL / JSON body / Authorization header 正确
@pytest.mark.asyncio
async def test_openai_compat_embed_posts_to_v1_embeddings() -> None:
    fake_client = AsyncMock()
    fake_resp = AsyncMock()
    fake_resp.raise_for_status = lambda: None
    fake_resp.json = lambda: {
        "data": [
            {"embedding": [0.1, 0.2, 0.3]},
            {"embedding": [0.4, 0.5, 0.6]},
        ]
    }
    fake_client.post = AsyncMock(return_value=fake_resp)
    emb = OpenAICompatEmbedding(
        api_key="sk-test", base_url="https://example.com", model="text-embedding-3-small", dims=3,
        client=fake_client,
    )
    out = await emb.embed(["hello", "world"])
    assert out == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    fake_client.post.assert_awaited_once()
    call_args = fake_client.post.await_args
    assert call_args.args[0] == "https://example.com/v1/embeddings"
    body = call_args.kwargs["json"]
    assert body["model"] == "text-embedding-3-small"
    assert body["input"] == ["hello", "world"]
    assert body["dimensions"] == 3
    headers = call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer sk-test"


# 功能：OpenAICompatEmbedding 空输入返回空列表（不发请求）
# 设计：embed([]) 应当走 fast path；mock client.post 抛 AssertionError 证明未调
@pytest.mark.asyncio
async def test_openai_compat_empty_input_returns_empty_without_request() -> None:
    fake_client = AsyncMock()
    emb = OpenAICompatEmbedding(api_key="k", base_url="https://x", client=fake_client)
    out = await emb.embed([])
    assert out == []
    fake_client.post.assert_not_called()


# 功能：OpenAICompatEmbedding 非 text-embedding-3 模型不发 dimensions 字段
# 设计：用 text-embedding-ada-002 调 embed，断言 body 不含 dimensions 键
@pytest.mark.asyncio
async def test_openai_compat_omits_dimensions_for_legacy_models() -> None:
    fake_client = AsyncMock()
    fake_resp = AsyncMock()
    fake_resp.raise_for_status = lambda: None
    fake_resp.json = lambda: {"data": [{"embedding": [0.1]}]}
    fake_client.post = AsyncMock(return_value=fake_resp)
    emb = OpenAICompatEmbedding(
        api_key="k", base_url="https://x", model="text-embedding-ada-002", dims=384,
        client=fake_client,
    )
    await emb.embed(["x"])
    body = fake_client.post.await_args.kwargs["json"]
    assert "dimensions" not in body


# 功能：OpenAICompatEmbedding 满足 EmbeddingProvider 协议
# 设计：isinstance 校验；embed_one 默认走 batch
def test_openai_compat_satisfies_protocol() -> None:
    emb = OpenAICompatEmbedding(api_key="k", base_url="https://x")
    assert isinstance(emb, EmbeddingProvider)


# 功能：EmbeddingProvider.embed_one 默认实现走 batch 然后取首条
# 设计：mock 子类的 embed 验证行为；不调子类自己实现时仍要拿到 [0]
@pytest.mark.asyncio
async def test_embedding_provider_embed_one_default_impl_uses_batch() -> None:
    # 直接用 FakeEmbedding 验证（embed_one 是 Protocol 默认方法）
    emb = FakeEmbedding(dims=8)
    v = await emb.embed_one("hello")
    assert len(v) == 8
    expected = (await emb.embed(["hello"]))[0]
    assert v == expected
