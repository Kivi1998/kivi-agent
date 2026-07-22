from __future__ import annotations

_DEFAULT_CONTEXT_WINDOW = 128_000

# 合并原先分散在 AnthropicProvider 和 OpenAICompatProvider 里的模型窗口表
_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-opus-4-7": 200_000,
    "deepseek-v4-pro": 128_000,
    "deepseek-v4-flash": 128_000,
    "kimi-k2.6": 128_000,
}


# 返回指定模型的上下文窗口 token 数；未知模型返回默认回退值
def context_window_for(model: str) -> int:
    return _CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW)
