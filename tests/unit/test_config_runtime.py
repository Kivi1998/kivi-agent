"""ConfigRuntime 单元测试（agent: package-config-v4）。

8 个场景：
1. 默认值（不传 config / env）
2. TOML 加载
3. 环境变量覆盖 TOML
4. 环境变量单独生效
5. 路径遍历保护
6. 错误处理（malformed TOML）
7. 切换标志（auto_fallback）
8. 健康检查配置
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from kivi_agent.core.config_runtime import ConfigRuntime


# 功能：默认值（不传 config_path / env）应返回 RuntimeConfig 的 dataclass 默认值
# 设计：不传任何参数，确认 8 个核心字段都是 dataclass 默认值
def test_defaults_when_no_toml_no_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 清除测试关心的所有 KIVI_* 环境变量
    for k in (
        "KIVI_RAG_MODE", "KIVI_RAG_API_URL", "KIVI_RAG_TIMEOUT_S",
        "KIVI_DB_MODE", "KIVI_DATABASE_URL",
        "KIVI_HEALTH_INTERVAL_S", "KIVI_HEALTH_TIMEOUT_S",
        "KIVI_AUTO_FALLBACK",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)

    cfg = ConfigRuntime.load()

    assert cfg.rag_mode == "mock"
    assert cfg.rag_api_url == "http://localhost:8001"
    assert cfg.rag_timeout_s == 5.0
    assert cfg.db_mode == "mock"
    assert cfg.database_url == "sqlite:///~/.kivi/test.db"
    assert cfg.health_check_interval_s == 60.0
    assert cfg.health_check_timeout_s == 3.0
    assert cfg.auto_fallback is True
    assert cfg.sources == {}


# 功能：TOML 配置文件正确解析并写入 RuntimeConfig
# 设计：写一个完整 TOML 到 tmp_path，验证 4 个小节都被正确解析 + sources 标记为 toml:<path>
def test_toml_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "KIVI_RAG_MODE", "KIVI_DB_MODE",
        "KIVI_HEALTH_INTERVAL_S", "KIVI_AUTO_FALLBACK",
    ):
        monkeypatch.delenv(k, raising=False)
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(
        """
# auto_fallback 必须在所有 [section] 之前才能成为顶层 key
auto_fallback = false

[rag]
mode = "http"
api_url = "http://rag.example.com:9000"
timeout_s = 12.5

[db]
mode = "sqlite"
database_url = "sqlite:////tmp/test.db"

[health]
interval_s = 30.0
timeout_s = 1.5
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    cfg = ConfigRuntime.load(config_path=toml_path)

    assert cfg.rag_mode == "http"
    assert cfg.rag_api_url == "http://rag.example.com:9000"
    assert cfg.rag_timeout_s == 12.5
    assert cfg.db_mode == "sqlite"
    assert cfg.database_url == "sqlite:////tmp/test.db"
    assert cfg.health_check_interval_s == 30.0
    assert cfg.health_check_timeout_s == 1.5
    assert cfg.auto_fallback is False
    # sources 标记
    assert cfg.sources["rag_mode"].startswith("toml:")
    assert cfg.sources["db_mode"].startswith("toml:")


# 功能：环境变量优先级高于 TOML（验证 env > toml > defaults）
# 设计：TOML 写一个值，env 写另一个值，确认 env 胜出 + sources 标记为 env:VAR
def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "config.toml"
    toml_path.write_text(
        '[rag]\nmode = "mock"\napi_url = "http://from-toml:1234"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KIVI_RAG_MODE", "http")
    monkeypatch.setenv("KIVI_RAG_API_URL", "http://from-env:5678")

    cfg = ConfigRuntime.load(config_path=toml_path)

    assert cfg.rag_mode == "http"
    assert cfg.rag_api_url == "http://from-env:5678"
    assert cfg.sources["rag_mode"] == "env:KIVI_RAG_MODE"
    assert cfg.sources["rag_api_url"] == "env:KIVI_RAG_API_URL"


# 功能：仅环境变量生效（不传 config_path），所有字段来自 env
# 设计：env 设置多个变量，验证每个都被读取；sources 全部为 env 标记
def test_env_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 先把可能影响结果的环境变量清掉
    for k in (
        "KIVI_RAG_MODE", "KIVI_RAG_API_URL", "KIVI_RAG_TIMEOUT_S",
        "KIVI_DB_MODE", "KIVI_DATABASE_URL",
        "KIVI_HEALTH_INTERVAL_S", "KIVI_HEALTH_TIMEOUT_S",
        "KIVI_AUTO_FALLBACK",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("KIVI_RAG_MODE", "http")
    monkeypatch.setenv("KIVI_RAG_API_URL", "http://env-only:9999")
    monkeypatch.setenv("KIVI_RAG_TIMEOUT_S", "7.5")
    monkeypatch.setenv("KIVI_DB_MODE", "postgres")
    monkeypatch.setenv("KIVI_AUTO_FALLBACK", "true")
    monkeypatch.chdir(tmp_path)

    cfg = ConfigRuntime.load()

    assert cfg.rag_mode == "http"
    assert cfg.rag_api_url == "http://env-only:9999"
    assert cfg.rag_timeout_s == 7.5
    assert cfg.db_mode == "postgres"
    assert cfg.auto_fallback is True
    assert all(v.startswith("env:") for v in cfg.sources.values())


# 功能：路径遍历保护——config_path 解析后落在 base_dir 之外时拒绝加载
# 设计：从 tmp_path 内通过 ../etc/passwd 逃逸，确认抛 ValueError
def test_path_traversal_protection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    # 从 tmp_path 内通过 ../etc/passwd 逃逸
    malicious = Path("../etc/passwd")

    with pytest.raises(ValueError, match="escapes base_dir"):
        ConfigRuntime.load(config_path=malicious)


# 功能：malformed TOML 应透传 tomllib.TOMLDecodeError（与 core/config.py 行为一致）
# 设计：写一个非法的 TOML，断言捕获标准库异常
def test_malformed_toml_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "bad.toml"
    toml_path.write_text("[rag\nmode = ", encoding="utf-8")  # 缺右括号
    monkeypatch.chdir(tmp_path)

    with pytest.raises(tomllib.TOMLDecodeError):
        ConfigRuntime.load(config_path=toml_path)


# 功能：auto_fallback 环境变量支持 truthy / falsy 写法（true/false）+ sources 标记
# 设计：分别验证 truthy 和 falsy 两种解析 + TOML 真值都被正确读取
def test_auto_fallback_toggle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Truthy from env
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KIVI_AUTO_FALLBACK", "true")
    cfg = ConfigRuntime.load()
    assert cfg.auto_fallback is True
    assert cfg.sources["auto_fallback"] == "env:KIVI_AUTO_FALLBACK"

    # Falsy from env
    monkeypatch.setenv("KIVI_AUTO_FALLBACK", "false")
    cfg = ConfigRuntime.load()
    assert cfg.auto_fallback is False

    # Falsy from TOML
    toml_path = tmp_path / "cfg.toml"
    toml_path.write_text("auto_fallback = false\n", encoding="utf-8")
    monkeypatch.delenv("KIVI_AUTO_FALLBACK", raising=False)
    cfg = ConfigRuntime.load(config_path=toml_path)
    assert cfg.auto_fallback is False
    assert cfg.sources["auto_fallback"].startswith("toml:")


# 功能：健康检查相关配置（interval / timeout）从 env 正确读取
# 设计：env 写入两个字段，验证被正确解析 + sources 标记
def test_health_check_config_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KIVI_HEALTH_INTERVAL_S", "15.0")
    monkeypatch.setenv("KIVI_HEALTH_TIMEOUT_S", "2.5")

    cfg = ConfigRuntime.load()

    assert cfg.health_check_interval_s == 15.0
    assert cfg.health_check_timeout_s == 2.5
    assert cfg.sources["health_check_interval_s"] == "env:KIVI_HEALTH_INTERVAL_S"
    assert cfg.sources["health_check_timeout_s"] == "env:KIVI_HEALTH_TIMEOUT_S"
