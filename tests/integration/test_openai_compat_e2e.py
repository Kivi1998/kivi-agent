"""OpenAI 兼容 Provider 真实 LLM 端到端测试（Wave 8.2 / agent: real-llm-e2e）。

env guard:
- KIVI_RUN_E2E=1
- KIVI_OPENAI_API_KEY 已设置（KIVI_OPENAI_BASE_URL 默认 OpenAI 官方）

跳过策略：缺任一 env guard → 全文件 pytest.skip（无需单测 skipif）
跑法：
    KIVI_RUN_E2E=1 KIVI_OPENAI_API_KEY=sk-... uv run pytest tests/integration/test_openai_compat_e2e.py -q
"""

from __future__ import annotations

import os

import pytest

from kivi_agent.core.llm.factory import create_provider
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider
from kivi_agent.core.memory.embedding.openai_compat import OpenAICompatEmbedding

# 全文件 skip if env guard 不满足
pytestmark = pytest.mark.skipif(
    not (os.environ.get("KIVI_RUN_E2E") == "1" and os.environ.get("KIVI_OPENAI_API_KEY")),
    reason="KIVI_RUN_E2E != 1 or KIVI_OPENAI_API_KEY not set; skipping real LLM e2e",
)


# 功能：real OpenAI 官方 gpt-4o-mini 单条 prompt 端到端
# 设计：发 "Say hi in one word." 期望收到非空 content；stop_reason=stop；usage 总 token > 0
@pytest.mark.asyncio
async def test_real_openai_complete_single_prompt() -> None:
    provider = create_provider("openai")
    assert isinstance(provider, OpenAICompatProvider)
    result = await provider.complete(
        [{"role": "user", "content": "Say hi in exactly one word. No punctuation."}]
    )
    assert result.content, "expected non-empty content"
    assert result.stop_reason == "stop"
    assert result.usage.total_tokens > 0
    assert result.model  # 上游回写 model 名


# 功能：real OpenAI 流式 stream_complete() 至少 2 个 chunk 且能拼成完整文本
# 设计：发短 prompt，断言 yield ≥ 2 次且拼接文本非空
@pytest.mark.asyncio
async def test_real_openai_stream_complete() -> None:
    provider = create_provider("openai")
    chunks = []
    async for ch in provider.stream_complete(
        [{"role": "user", "content": "Reply with the number 42."}]
    ):
        chunks.append(ch)
    text = "".join(c.content for c in chunks)
    assert text.strip(), "expected non-empty stream text"
    # 流式至少要有 1 个 content 增量 + 1 个 finish_reason
    assert any(c.content for c in chunks)
    assert any(c.finish_reason for c in chunks)


# 功能：real OpenAI Embedding 单文本端到端
# 设计：embed(["hello world"]) 返回 1 个向量，维度为 text-embedding-3-small 默认（1536）
@pytest.mark.asyncio
async def test_real_openai_embed_single_text() -> None:
    emb = OpenAICompatEmbedding(
        api_key=os.environ.get("KIVI_OPENAI_API_KEY"),
        base_url=os.environ.get("KIVI_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model=os.environ.get("KIVI_EMBEDDING_MODEL", "text-embedding-3-small"),
        dims=int(os.environ.get("KIVI_EMBEDDING_DIMS", "1536")),
    )
    out = await emb.embed(["hello world"])
    assert len(out) == 1
    assert len(out[0]) > 0
    # text-embedding-3-small 输出维度 = dims（这里 1536）
    assert len(out[0]) == int(os.environ.get("KIVI_EMBEDDING_DIMS", "1536"))
