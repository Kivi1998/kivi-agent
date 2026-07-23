"""health router 单元测试（agent: package-config-v4）。

5 个场景：
1. mock rag 健康 → 200
2. 真实 rag 健康 → 200
3. 真实 rag 不健康 → 207 degraded
4. mock db 健康 → 200
5. 双不健康 → 207 degraded

策略：构造带 `async health_check() -> bool` 方法的 fake 对象；
不依赖 WT-F1 / WT-F2 的真实 RagKbClient / DatabaseAdapter 类。
"""

from __future__ import annotations

from typing import Any

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient
from fastapi import FastAPI  # noqa: E402

from kivi_agent.gateway.health import build_health_router  # noqa: E402


# 满足 _HealthCheckable 协议的 fake（agent: package-config-v4）
class _FakeClient:
    """带 async health_check() 方法的 fake client（agent: package-config-v4）。"""

    def __init__(self, healthy: bool, url: str = "http://fake:1234") -> None:
        self._healthy = healthy
        self._base_url = url

    async def health_check(self) -> bool:
        return self._healthy


class _FakeDbAdapter:
    """带 async health_check() + _db_path 的 fake DB adapter（agent: package-config-v4）。"""

    def __init__(self, healthy: bool, db_path: str = "/tmp/test.db") -> None:
        self._healthy = healthy
        self._db_path = db_path

    async def health_check(self) -> bool:
        return self._healthy


# 构造带 health/detailed 端点的最小 FastAPI app
def _build_app(rag_client: Any, db_adapter: Any) -> FastAPI:
    """构造只挂 /health/detailed 路由的最小 app（agent: package-config-v4）。"""
    app = FastAPI()
    app.include_router(build_health_router(rag_client, db_adapter))
    return app


# 功能：mock rag（rag_client=None）+ mock db → status=healthy / 200
# 设计：两个参数都传 None，确认 200 + healthy + 两个 service 的 mode 都是 "mock"
def test_mock_rag_and_mock_db_returns_200() -> None:
    app = _build_app(rag_client=None, db_adapter=None)
    with TestClient(app) as c:
        resp = c.get("/health/detailed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["services"]["rag"] == {"mode": "mock", "healthy": True, "url": None}
    assert body["services"]["db"] == {"mode": "mock", "healthy": True, "url": None}


# 功能：真实 rag 健康 + mock db → 200 + healthy
# 设计：构造 healthy rag client + None db，验证 mode="http" + url 被提取
def test_real_rag_healthy_returns_200() -> None:
    rag = _FakeClient(healthy=True, url="http://rag:8001")
    app = _build_app(rag_client=rag, db_adapter=None)
    with TestClient(app) as c:
        resp = c.get("/health/detailed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["services"]["rag"]["mode"] == "http"
    assert body["services"]["rag"]["healthy"] is True
    assert body["services"]["rag"]["url"] == "http://rag:8001"
    # db 仍是 mock
    assert body["services"]["db"]["mode"] == "mock"


# 功能：真实 rag 不健康 + mock db → 207 + degraded（rag.healthy=false）
# 设计：构造 unhealthy rag client，验证 207 + status=degraded
def test_real_rag_unhealthy_returns_207() -> None:
    rag = _FakeClient(healthy=False, url="http://rag:8001")
    app = _build_app(rag_client=rag, db_adapter=None)
    with TestClient(app) as c:
        resp = c.get("/health/detailed")
    assert resp.status_code == 207
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["services"]["rag"]["healthy"] is False
    # db 仍健康（mock 永远 True）
    assert body["services"]["db"]["healthy"] is True


# 功能：mock rag + 真实 db 健康 → 200 + healthy
# 设计：构造 healthy db adapter（带 _db_path）+ None rag，验证 mode="real" + url 被提取
def test_mock_rag_and_real_db_healthy_returns_200() -> None:
    db = _FakeDbAdapter(healthy=True, db_path="/tmp/test.db")

    app = _build_app(rag_client=None, db_adapter=db)
    with TestClient(app) as c:
        resp = c.get("/health/detailed")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["services"]["db"]["mode"] == "real"
    assert body["services"]["db"]["healthy"] is True
    # _db_path 字段被正确提取
    assert body["services"]["db"]["url"] == "/tmp/test.db"


# 功能：双不健康（rag + db 都 false）→ 207 + degraded
# 设计：两个 fake 都 healthy=False，验证 207 + 两个 service 都 false
def test_both_unhealthy_returns_207() -> None:
    rag = _FakeClient(healthy=False, url="http://rag:8001")
    db = _FakeDbAdapter(healthy=False, db_path="/tmp/bad.db")
    app = _build_app(rag_client=rag, db_adapter=db)
    with TestClient(app) as c:
        resp = c.get("/health/detailed")
    assert resp.status_code == 207
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["services"]["rag"]["healthy"] is False
    assert body["services"]["db"]["healthy"] is False
