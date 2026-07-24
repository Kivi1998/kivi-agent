from __future__ import annotations

from unittest.mock import patch

import pytest

from kivi_agent.core.llm.factory import (
    _FakeLLMProvider,
    create_provider,
)
from kivi_agent.core.llm.provider import AnthropicProvider

# --- 默认行为：无 env vars 时回退 fake ------------------------------------


# 功能：验证没有设置 KIVI_ANTHROPIC_API_KEY 时，create_provider('anthropic') 返回 fake
# 设计：保留 Wave 1 行为：默认 provider 不要求真 key，避免破坏现有 1425+ 测试
def test_default_anthropic_no_key_returns_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KIVI_ANTHROPIC_API_KEY", raising=False)
    provider = create_provider("anthropic", model="m")
    assert isinstance(provider, _FakeLLMProvider)
    assert provider._model == "m"


# 功能：验证 create_provider 默认参数 provider_name='anthropic'
# 设计：覆盖默认调用约定（与原 Wave 1 factory 行为一致）
def test_default_provider_name_is_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KIVI_ANTHROPIC_API_KEY", raising=False)
    provider = create_provider()
    assert isinstance(provider, _FakeLLMProvider)


# --- KIVI_ANTHROPIC_API_KEY 设置时返回真 provider -------------------------


# 功能：验证设置 KIVI_ANTHROPIC_API_KEY 后 create_provider('anthropic') 返回 AnthropicProvider
# 设计：覆盖真实 LLM 接入路径，env 隔离避免污染其他测试；mock AsyncAnthropic
# 防止真的去连 Anthropic API
def test_anthropic_with_key_returns_real_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIVI_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("KIVI_ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("KIVI_LLM_DEFAULT_MODEL", raising=False)
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic") as mock_cls:
        provider = create_provider("anthropic", model="claude-test")
    assert isinstance(provider, AnthropicProvider)
    assert provider._model == "claude-test"
    mock_cls.assert_called_once_with(api_key="sk-ant-test")


# 功能：验证 KIVI_ANTHROPIC_BASE_URL 被透传给 provider（支持 DeepSeek 兼容端点）
def test_anthropic_base_url_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIVI_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("KIVI_ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic") as mock_cls:
        provider = create_provider("anthropic", model="m")
    assert isinstance(provider, AnthropicProvider)
    assert provider._base_url == "https://api.deepseek.com/anthropic"
    mock_cls.assert_called_once_with(
        api_key="sk-ant-test",
        base_url="https://api.deepseek.com/anthropic",
    )


# 功能：验证 KIVI_LLM_DEFAULT_MODEL 作为 model 默认值（model=None 时读取）
def test_anthropic_default_model_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIVI_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("KIVI_LLM_DEFAULT_MODEL", "claude-opus-4-6")
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic"):
        provider = create_provider("anthropic")
    assert provider._model == "claude-opus-4-6"


# --- timeout / max_retries env vars ---------------------------------------


# 功能：验证 KIVI_LLM_TIMEOUT 字符串被解析为 float
def test_timeout_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIVI_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("KIVI_LLM_TIMEOUT", "12.5")
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic"):
        provider = create_provider("anthropic", model="m")
    assert provider._timeout == 12.5


# 功能：验证 KIVI_LLM_MAX_RETRIES 字符串被解析为 int
def test_max_retries_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIVI_ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("KIVI_LLM_MAX_RETRIES", "5")
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic"):
        provider = create_provider("anthropic", model="m")
    assert provider._max_retries == 5


# --- explicit provider_name="fake" ---------------------------------------


# 功能：验证 provider_name='fake' 显式返回 _FakeLLMProvider
def test_explicit_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KIVI_ANTHROPIC_API_KEY", raising=False)
    provider = create_provider("fake", model="any")
    assert isinstance(provider, _FakeLLMProvider)


# --- 非法 provider_name ---------------------------------------------------


# 功能：验证未知 provider_name 抛出 ValueError（防止 typo 静默 fallback）
def test_unknown_provider_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KIVI_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Unknown provider"):
        create_provider("gpt99", model="m")
