"""E2E 真实接入测试共享 conftest（agent: package-e2e-real-v4 + package-e2e-real-w82）。

# conftest.py（agent: package-e2e-real-v4 + package-e2e-real-w82）
WT-F4 E2E 特殊处理：

1. **本地代理旁路**：开发机通常设了 ``http_proxy`` / ``all_proxy``（如 Clash/SSR），
   会拦截 ``127.0.0.1`` 请求返回 502。本模块在 import 时立即把
   ``127.0.0.1`` / ``localhost`` 加入 ``NO_PROXY``，确保 in-process mock server
   与 ``httpx`` 客户端直连不走代理。

2. **共享 fixture（v4）**：
   - ``rag_server``: 启停 in-process rag-kb mock
   - ``postgres_dsn``: 从环境变量构造 Postgres DSN（默认对齐 docker-compose.test.yml）

3. **WT-L3 fixture（w82）**：真实 LLM 端到端测试
   - ``env_guard``: ``KIVI_RUN_E2E != "1"`` 时整个 session 自动 skip
   - ``llm_provider``: 按 ``KIVI_E2E_PROVIDER`` (anthropic/openai) 构造 LLM provider；
     缺 API key / 模块不可用时返回 None，调用方决定 fail 还是 skip
   - ``max_cases``: 读 ``KIVI_E2E_MAX_CASES``（默认 5）限制 case 数
   - ``report_dir``: 读 ``KIVI_E2E_REPORT_DIR``（默认 ``reports/e2e_real/``）

设计要点：
- 纯逻辑（读 env + 返回值）抽到模块级函数，便于单元测试
- pytest fixture 只是简单包装，pytest.skip 决策由 ``is_e2e_enabled()`` 决定
- 真实 provider 构造延迟到 ``_build_*_provider()`` 内部 import，
  集成期 main agent 在 ``tests/e2e_real/_runtime_provider.py`` 注入实际实现
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

# 在 import 时立即设置，避免后续 httpx / requests 走代理拦截 127.0.0.1（agent: package-e2e-real-v4）
# 注意：必须放在最顶端，import 任何 httpx 之前
_LOOPBACK_NO_PROXY = "127.0.0.1,localhost,::1"
for _k in ("NO_PROXY", "no_proxy"):
    _existing = os.environ.get(_k, "")
    if _existing:
        # 已有的项保留（用户显式设的域名），把 loopback 追加进去
        _parts = {p.strip() for p in _existing.split(",") if p.strip()}
        _parts.update({"127.0.0.1", "localhost", "::1"})
        os.environ[_k] = ",".join(sorted(_parts))
    else:
        os.environ[_k] = _LOOPBACK_NO_PROXY

import pytest  # noqa: E402  # 必须在 NO_PROXY 设置后 import

from tests.e2e_real.report import E2EReport  # noqa: E402
from tests.fixtures.rag_kb_mock_server import InProcessRagKbServer  # noqa: E402

# ---------------------------------------------------------------------------
# WT-L3 纯函数（可单元测试）
# ---------------------------------------------------------------------------


# 判断 e2e 是否启用（agent: package-e2e-real-w82）
def is_e2e_enabled(env: dict[str, str] | None = None) -> bool:
    """``KIVI_RUN_E2E == "1"`` 时返回 True；否则 False（默认禁用）。"""
    src = env if env is not None else os.environ
    return src.get("KIVI_RUN_E2E") == "1"


# 解析 provider 名（agent: package-e2e-real-w82）
def resolve_provider_name(env: dict[str, str] | None = None) -> str:
    """读 ``KIVI_E2E_PROVIDER`` 并归一化为小写；非法值回退 anthropic。"""
    src = env if env is not None else os.environ
    raw = src.get("KIVI_E2E_PROVIDER", "anthropic").strip().lower()
    if raw in ("anthropic", "openai"):
        return raw
    return "anthropic"


# 解析 max_cases 整数（agent: package-e2e-real-w82）
def resolve_max_cases(env: dict[str, str] | None = None) -> int:
    """读 ``KIVI_E2E_MAX_CASES``（默认 5）；非法或非正数 → 5。"""
    src = env if env is not None else os.environ
    raw = src.get("KIVI_E2E_MAX_CASES", "5")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 5
    return max(1, value)


# 解析 report 目录（agent: package-e2e-real-w82）
def resolve_report_dir(env: dict[str, str] | None = None) -> Path:
    """读 ``KIVI_E2E_REPORT_DIR``（默认 ``reports/e2e_real/``）；不创建目录。"""
    src = env if env is not None else os.environ
    raw = src.get("KIVI_E2E_REPORT_DIR", "reports/e2e_real/").strip()
    if not raw:
        raw = "reports/e2e_real/"
    p = Path(raw)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


# ---------------------------------------------------------------------------
# WT-F4 v4 fixture（保留向后兼容）
# ---------------------------------------------------------------------------


# 启动并 yield in-process rag-kb mock server（agent: package-e2e-real-v4）
@pytest.fixture
def rag_server() -> Generator[str, None, None]:
    """启动 in-process rag-kb mock，yield base_url，结束时停机。

    用法：
    ```python
    def test_xxx(rag_server: str):
        r = httpx.get(f'{rag_server}/health')
        ...
    ```
    """
    server = InProcessRagKbServer()
    base_url = server.start()
    try:
        yield base_url
    finally:
        server.stop()


# 启动并 yield 带自定义 docs 的 mock server（agent: package-e2e-real-v4）
@pytest.fixture
def rag_server_custom_docs() -> Generator[str, None, None]:
    """启动带 1 条自定义 doc 的 mock server，验证注入场景。"""
    custom: list[dict[str, object]] = [
        {
            "id": "custom-1",
            "title": "Custom Doc",
            "snippet": "custom test snippet",
            "score": 0.99,
            "url": "https://example.com/custom",
        }
    ]
    server = InProcessRagKbServer(kb_id="custom", custom_docs=custom)
    base_url = server.start()
    try:
        yield base_url
    finally:
        server.stop()


# 构造 Postgres DSN（agent: package-e2e-real-v4）
@pytest.fixture
def postgres_dsn() -> str:
    """从环境变量 DATABASE_URL 读 Postgres DSN；未设则用 docker-compose.test.yml 默认值。"""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://kivi_test:kivi_test@127.0.0.1:5432/kivi_test",
    )


# ---------------------------------------------------------------------------
# WT-L3 fixture（Wave 8.2 真实 LLM E2E 框架）
# ---------------------------------------------------------------------------


# env guard fixture（agent: package-e2e-real-w82）
@pytest.fixture(scope="session")
def env_guard() -> None:
    """``KIVI_RUN_E2E != "1"`` 时 pytest.skip（统一收敛所有 e2e_real 跳过条件）。

    session-scoped：与 ``e2e_report`` 共享；只需 session 开始时检查 1 次。
    """
    if not is_e2e_enabled():
        pytest.skip("KIVI_RUN_E2E not set; set KIVI_RUN_E2E=1 to run e2e_real tests")


# Anthropic provider 构造（agent: package-e2e-real-w82）
def _build_anthropic_provider() -> Any:
    """延迟 import 真实 Anthropic provider（集成期 main agent 在 _runtime_provider 注入）。"""
    from tests.e2e_real._runtime_provider import (
        build_anthropic_provider,  # type: ignore[import-not-found]
    )

    return build_anthropic_provider()


# OpenAI 兼容 provider 构造（agent: package-e2e-real-w82）
def _build_openai_provider() -> Any:
    """延迟 import 真实 OpenAI 兼容 provider（集成期 main agent 在 _runtime_provider 注入）。"""
    from tests.e2e_real._runtime_provider import (
        build_openai_provider,  # type: ignore[import-not-found]
    )

    return build_openai_provider()


# llm_provider fixture（agent: package-e2e-real-w82）
@pytest.fixture
def llm_provider(env_guard: None) -> Any:
    """按 ``KIVI_E2E_PROVIDER`` (anthropic/openai) 构造 LLM provider。

    行为：
    - 缺 API key / 缺依赖模块 / 异常 → 返回 None（测试自行决定 fail/skip）
    - 成功 → 返回 ``LLMSimpleProvider`` 协议实例（由集成期 main agent 注入）
    """
    name = resolve_provider_name()
    try:
        if name == "anthropic":
            return _build_anthropic_provider()
        if name == "openai":
            return _build_openai_provider()
    except Exception:
        # 集成期 main agent 会处理；这里 swallow，让测试决定如何应对
        return None
    return None


# max_cases fixture（agent: package-e2e-real-w82）
@pytest.fixture
def max_cases() -> int:
    """读 ``KIVI_E2E_MAX_CASES``（默认 5），限制 e2e case 数避免 token 失控。"""
    return resolve_max_cases()


# report_dir fixture（agent: package-e2e-real-w82）
@pytest.fixture(scope="session")
def report_dir(env_guard: None) -> Path:
    """读 ``KIVI_E2E_REPORT_DIR``（默认 ``reports/e2e_real/``）；自动 mkdir。"""
    p = resolve_report_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


# 共享 session-scoped report fixture（agent: package-e2e-real-w82）
@pytest.fixture(scope="session")
def e2e_report(env_guard: None) -> Generator[E2EReport, None, None]:
    """session-scoped E2EReport：所有 e2e_real test 共享同一份聚合报告。"""
    report = E2EReport()
    yield report
    # session 结束时落盘
    if report.results:
        out_dir = resolve_report_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        base = out_dir / "real_llm_e2e_run"
        report.to_json(base.with_suffix(".json"))
        report.to_markdown(base.with_suffix(".md"))


__all__ = [
    "e2e_report",
    "env_guard",
    "is_e2e_enabled",
    "llm_provider",
    "max_cases",
    "postgres_dsn",
    "rag_server",
    "rag_server_custom_docs",
    "report_dir",
    "resolve_max_cases",
    "resolve_provider_name",
    "resolve_report_dir",
]
