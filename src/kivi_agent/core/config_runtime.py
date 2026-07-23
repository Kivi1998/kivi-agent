"""运行时配置（agent: package-config-v4）。

加载顺序：环境变量 > TOML 配置文件 > 默认值。
配置项覆盖 Wave 4 Adapter 选择 + 健康检查 + 切换机制。

与 `core.config.KamaConfig` 并存：KamaConfig 负责 core 守护进程自身配置
（host / port / logging / llm / trace 等），本模块只关心 Wave 4 新增的
RAG / DB Adapter 选择 + 健康检查 + 失败降级开关。
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

# TOML 合法值集合（rag / db mode）
_VALID_RAG_MODES = frozenset({"mock", "http"})
_VALID_DB_MODES = frozenset({"mock", "sqlite", "postgres"})

# 路径遍历保护基目录：缺省 = 当前工作目录
_DEFAULT_BASE_DIR = Path(".")


@dataclass
class RuntimeConfig:
    """运行时配置（agent: package-config-v4）。

    字段含义：
    - `rag_mode` / `db_mode`: Adapter 选择；`mock` = 演示版（默认），其余为真实接入
    - `*_api_url` / `database_url`: 真实服务地址（仅 *_mode != "mock" 时生效）
    - `health_check_interval_s` / `health_check_timeout_s`: 健康检查节奏
    - `auto_fallback`: 真实服务不可用时是否自动降级到 Mock
    - `sources`: 字段 -> 来源标识（`env:VAR` / `toml:<path>` / `default`），便于诊断
    """

    # RAG
    rag_mode: Literal["mock", "http"] = "mock"
    rag_api_url: str = "http://localhost:8001"
    rag_timeout_s: float = 5.0

    # DB
    db_mode: Literal["mock", "sqlite", "postgres"] = "mock"
    database_url: str = "sqlite:///~/.kivi/test.db"

    # 健康检查
    health_check_interval_s: float = 60.0
    health_check_timeout_s: float = 3.0

    # 切换
    auto_fallback: bool = True

    # 加载来源（追踪）：key -> "env:VAR" | "toml:path" | "default"
    sources: dict[str, str] = field(default_factory=dict)


# 解析后路径是否落在 base 之内（路径遍历保护）
def _is_within(path: Path, base: Path) -> bool:
    """判断 path 是否为 base 的子路径（agent: package-config-v4）。

    通过 `Path.relative_to` 试探：若 path 不在 base 之下，relative_to 抛 ValueError。
    """
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


class ConfigRuntime:
    """加载并持有 RuntimeConfig（agent: package-config-v4）。"""

    @staticmethod
    def load(
        config_path: Path | None = None,
        env: dict[str, str] | None = None,
        base_dir: Path | None = None,
    ) -> RuntimeConfig:
        """按 环境变量 > TOML > 默认值 顺序加载（agent: package-config-v4）。

        参数：
        - `config_path`: 可选 TOML 配置文件路径；为 None 时跳过 TOML 加载
        - `env`: 可选环境变量字典（测试注入用）；为 None 时用 `os.environ`
        - `base_dir`: 路径遍历基目录（测试可注入）；缺省 = 当前工作目录

        抛出：
        - `ValueError`: config_path 解析后落在 base_dir 之外（路径遍历保护）
        - `tomllib.TOMLDecodeError`: TOML 解析失败（透传）
        """
        env = env or dict(os.environ)
        base = (base_dir or _DEFAULT_BASE_DIR).resolve()
        config = RuntimeConfig()

        # 1) TOML 文件加载（带路径遍历保护）
        if config_path is not None:
            try:
                resolved = config_path.resolve()
            except (OSError, RuntimeError) as exc:
                raise ValueError(f"invalid config_path {config_path}: {exc}") from exc
            if not _is_within(resolved, base):
                raise ValueError(
                    f"config_path escapes base_dir: "
                    f"path={config_path}, base={base}"
                )
            if resolved.exists():
                with open(resolved, "rb") as f:
                    data = tomllib.load(f)
                _apply_toml(config, data, resolved)

        # 2) 环境变量（覆盖 TOML；最高优先级）
        _apply_env(config, env)

        return config


# 将 TOML 字典写入 config（不认识的键静默忽略；类型错误时抛 TOMLDecodeError 由 tomllib 处理）
def _apply_toml(config: RuntimeConfig, data: dict[str, Any], path: Path) -> None:
    """从 TOML 根表写入 RuntimeConfig（agent: package-config-v4）。"""
    src = f"toml:{path}"

    # [rag]
    rag = data.get("rag")
    if isinstance(rag, dict):
        if "mode" in rag:
            val = rag["mode"]
            if val not in _VALID_RAG_MODES:
                raise ValueError(
                    f"config rag.mode must be one of {sorted(_VALID_RAG_MODES)}, got: {val!r}"
                )
            config.rag_mode = val
            config.sources["rag_mode"] = src
        if "api_url" in rag:
            val = rag["api_url"]
            if not isinstance(val, str):
                raise ValueError("config rag.api_url must be a string")
            config.rag_api_url = val
        if "timeout_s" in rag:
            val = rag["timeout_s"]
            if not isinstance(val, (int, float)) or val <= 0:
                raise ValueError("config rag.timeout_s must be a positive number")
            config.rag_timeout_s = float(val)

    # [db]
    db = data.get("db")
    if isinstance(db, dict):
        if "mode" in db:
            val = db["mode"]
            if val not in _VALID_DB_MODES:
                raise ValueError(
                    f"config db.mode must be one of {sorted(_VALID_DB_MODES)}, got: {val!r}"
                )
            config.db_mode = val
            config.sources["db_mode"] = src
        if "database_url" in db:
            val = db["database_url"]
            if not isinstance(val, str):
                raise ValueError("config db.database_url must be a string")
            config.database_url = val

    # [health]
    health = data.get("health")
    if isinstance(health, dict):
        if "interval_s" in health:
            val = health["interval_s"]
            if not isinstance(val, (int, float)) or val <= 0:
                raise ValueError("config health.interval_s must be a positive number")
            config.health_check_interval_s = float(val)
        if "timeout_s" in health:
            val = health["timeout_s"]
            if not isinstance(val, (int, float)) or val <= 0:
                raise ValueError("config health.timeout_s must be a positive number")
            config.health_check_timeout_s = float(val)

    # 顶层 auto_fallback（TOML 中需在 [health] 段之前；段后会被并入 [health]）
    if "auto_fallback" in data:
        val = data["auto_fallback"]
        if not isinstance(val, bool):
            raise ValueError("config auto_fallback must be a boolean")
        config.auto_fallback = val
        config.sources["auto_fallback"] = src


# 用 KIVI_* 环境变量覆盖 config（仅当变量已设置）
def _apply_env(config: RuntimeConfig, env: dict[str, str]) -> None:
    """用 KIVI_* 环境变量覆盖 config（agent: package-config-v4）。"""

    # RAG
    if "KIVI_RAG_MODE" in env:
        val = env["KIVI_RAG_MODE"]
        if val not in _VALID_RAG_MODES:
            raise ValueError(
                f"KIVI_RAG_MODE must be one of {sorted(_VALID_RAG_MODES)}, got: {val!r}"
            )
        config.rag_mode = val  # type: ignore[assignment]
        config.sources["rag_mode"] = "env:KIVI_RAG_MODE"
    if "KIVI_RAG_API_URL" in env:
        config.rag_api_url = env["KIVI_RAG_API_URL"]
        config.sources["rag_api_url"] = "env:KIVI_RAG_API_URL"
    if "KIVI_RAG_TIMEOUT_S" in env:
        try:
            v = float(env["KIVI_RAG_TIMEOUT_S"])
        except ValueError as exc:
            raise ValueError(
                f"KIVI_RAG_TIMEOUT_S must be a number, got: {env['KIVI_RAG_TIMEOUT_S']!r}"
            ) from exc
        if v <= 0:
            raise ValueError(f"KIVI_RAG_TIMEOUT_S must be > 0, got: {v!r}")
        config.rag_timeout_s = v
        config.sources["rag_timeout_s"] = "env:KIVI_RAG_TIMEOUT_S"

    # DB
    if "KIVI_DB_MODE" in env:
        val = env["KIVI_DB_MODE"]
        if val not in _VALID_DB_MODES:
            raise ValueError(
                f"KIVI_DB_MODE must be one of {sorted(_VALID_DB_MODES)}, got: {val!r}"
            )
        config.db_mode = val  # type: ignore[assignment]
        config.sources["db_mode"] = "env:KIVI_DB_MODE"
    if "KIVI_DATABASE_URL" in env:
        config.database_url = env["KIVI_DATABASE_URL"]
        config.sources["database_url"] = "env:KIVI_DATABASE_URL"

    # Health
    if "KIVI_HEALTH_INTERVAL_S" in env:
        try:
            v = float(env["KIVI_HEALTH_INTERVAL_S"])
        except ValueError as exc:
            raise ValueError(
                f"KIVI_HEALTH_INTERVAL_S must be a number, got: "
                f"{env['KIVI_HEALTH_INTERVAL_S']!r}"
            ) from exc
        if v <= 0:
            raise ValueError(f"KIVI_HEALTH_INTERVAL_S must be > 0, got: {v!r}")
        config.health_check_interval_s = v
        config.sources["health_check_interval_s"] = "env:KIVI_HEALTH_INTERVAL_S"
    if "KIVI_HEALTH_TIMEOUT_S" in env:
        try:
            v = float(env["KIVI_HEALTH_TIMEOUT_S"])
        except ValueError as exc:
            raise ValueError(
                f"KIVI_HEALTH_TIMEOUT_S must be a number, got: "
                f"{env['KIVI_HEALTH_TIMEOUT_S']!r}"
            ) from exc
        if v <= 0:
            raise ValueError(f"KIVI_HEALTH_TIMEOUT_S must be > 0, got: {v!r}")
        config.health_check_timeout_s = v
        config.sources["health_check_timeout_s"] = "env:KIVI_HEALTH_TIMEOUT_S"

    # 切换
    if "KIVI_AUTO_FALLBACK" in env:
        raw = env["KIVI_AUTO_FALLBACK"].lower()
        config.auto_fallback = raw in ("1", "true", "yes", "on")
        config.sources["auto_fallback"] = "env:KIVI_AUTO_FALLBACK"


__all__ = ["ConfigRuntime", "RuntimeConfig"]
