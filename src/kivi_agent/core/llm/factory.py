from __future__ import annotations

import os

from kivi_agent.core.config import KamaConfig
from kivi_agent.core.llm.base import LLMProvider
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider
from kivi_agent.core.llm.provider import AnthropicProvider


# 根据配置构造对应的 LLMProvider 实例（Anthropic 或 OpenAI 兼容）
def build_provider(config: KamaConfig) -> LLMProvider:
    if config.llm.provider == "openai_compat":
        base_url = config.llm.openai_base_url
        if not base_url:
            raise SystemExit("llm.openai_base_url must be set when llm.provider = 'openai_compat'")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY not set")
        return OpenAICompatProvider(config.llm.default_model, base_url=base_url, api_key=api_key)
    return AnthropicProvider(config.llm.default_model)
