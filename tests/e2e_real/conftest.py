"""E2E 真实接入测试共享 conftest（agent: package-e2e-real-v4）。

WT-F4 E2E 特殊处理：

1. **本地代理旁路**：开发机通常设了 ``http_proxy`` / ``all_proxy``（如 Clash/SSR），
   会拦截 ``127.0.0.1`` 请求返回 502。本模块在 import 时立即把
   ``127.0.0.1`` / ``localhost`` 加入 ``NO_PROXY``，确保 in-process mock server
   与 ``httpx`` 客户端直连不走代理。

2. **共享 fixture**：
   - ``rag_server``: 启停 in-process rag-kb mock
   - ``postgres_dsn``: 从环境变量构造 Postgres DSN（默认对齐 docker-compose.test.yml）
"""

from __future__ import annotations

import os
from collections.abc import Generator

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

from tests.fixtures.rag_kb_mock_server import InProcessRagKbServer  # noqa: E402


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


__all__ = [
    "rag_server",
    "rag_server_custom_docs",
    "postgres_dsn",
]
