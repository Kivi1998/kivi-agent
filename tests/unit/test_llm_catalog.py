from __future__ import annotations

from kama_claude.core.llm.catalog import context_window_for


# 功能：验证已知模型返回内建表里的精确窗口大小
# 设计：覆盖 Claude 和 DeepSeek 各一个已知型号，确认两个 provider 原来各自维护的表被正确合并
def test_known_models_return_exact_window() -> None:
    assert context_window_for("claude-sonnet-4-6") == 200_000
    assert context_window_for("deepseek-v4-pro") == 128_000


# 功能：验证未知模型名返回默认回退值而不是报错
# 设计：新模型上线但表还没更新时，不应该让整个对话崩掉，覆盖这个降级路径
def test_unknown_model_returns_default_fallback() -> None:
    assert context_window_for("some-brand-new-model-2027") == 128_000
