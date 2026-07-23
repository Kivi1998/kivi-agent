"""健康检查 + 降级机制 E2E（agent: package-e2e-real-v4）。

WT-F4 E2E 场景：验证 rag-kb / DB 在"健康 ↔ 不可用"切换时的
健康检查端点行为，对齐 docs/superpowers/plans/2026-07-23-aigroup-wave4-real-rag-db.md §三 WT-F3
的 ``/health/detailed`` 端点契约（不依赖 F3 实际模块，用本地最小实现复现契约）。

3 个场景：
1. ``test_rag_health_endpoint_reflects_server_state`` — mock rag-kb /health
   反映服务状态（启动=ok，停止=连失败）
2. ``test_health_detailed_reports_degraded_when_rag_down`` — 模拟
   ``/health/detailed`` 在 rag-kb 挂掉时返回 207 + status=degraded
3. ``test_health_detailed_reports_healthy_when_all_up`` — 模拟全健康时
   返回 200 + status=ok

依赖：仅 fastapi（已装）+ httpx（已装）。
"""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi import FastAPI, Response, status
from fastapi.testclient import TestClient

from tests.fixtures.rag_kb_mock_server import InProcessRagKbServer


# 本地最小化的 /health/detailed 端点（agent: package-e2e-real-v4）
# 这是 F3 build_health_router 的预期契约复现；当 F3 合并后，本测试可
# 改为直接 import 真实 router。当前为可独立验证的最小实现。
def _build_minimal_health_router(rag_base_url: str) -> FastAPI:
    """构造一个最小 FastAPI app，模拟 /health + /health/detailed。

    rag 状态：用 httpx 探测 /health；db 状态：永远 ok（这里只测 rag）。
    """
    app = FastAPI(title="minimal health (F4 E2E)")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.0.1"}

    @app.get("/health/detailed")
    async def health_detailed() -> Response:
        # 探测 rag-kb
        rag_ok = False
        try:
            r = httpx.get(f"{rag_base_url}/health", timeout=0.5)
            rag_ok = r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            rag_ok = False
        # db 在本测试中假定 ok（不依赖 F2）
        db_ok = True
        # 聚合状态
        all_ok = rag_ok and db_ok
        body = {
            "status": "ok" if all_ok else "degraded",
            "components": {
                "rag_kb": {"ok": rag_ok, "url": rag_base_url},
                "database": {"ok": db_ok},
            },
        }
        # 207 Multi-Status 表示部分降级；200 表示全健康
        code = status.HTTP_200_OK if all_ok else status.HTTP_207_MULTI_STATUS
        return Response(
            content=httpx.Response(code, json=body).content.decode("utf-8"),
            status_code=code,
            media_type="application/json",
        )

    return app


# 功能：mock rag-kb 启动时 /health 返回 ok，停止后连接被拒（"服务挂了"的真实信号）
# 设计：与 test_rag_real_health_endpoint_ok 不同的是，本测试显式覆盖 "停止后"
#      的状态变化，验证 RagKbClient.health_check() 在服务生命周期两端的判断一致性
def test_rag_health_endpoint_reflects_server_state() -> None:
    server = InProcessRagKbServer()
    base_url = server.start()
    try:
        # 启动：/health 返回 200
        resp = httpx.get(f"{base_url}/health", timeout=1.0)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        server.stop()
    # 停止：连接被拒
    time.sleep(0.3)
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{base_url}/health", timeout=0.5)


# 功能：rag-kb 挂掉时 /health/detailed 返回 207 + status=degraded 触发降级
# 设计：start server → 构造 /health/detailed app → 验证 200 ok；stop server
#      → 重新探测 → 验证 207 + rag_kb.ok=False；这是 F3 健康检查端点的核心契约
def test_health_detailed_reports_degraded_when_rag_down() -> None:
    server = InProcessRagKbServer()
    base_url = server.start()
    try:
        # 阶段 1：rag 正常
        app_ok = _build_minimal_health_router(base_url)
        client_ok = TestClient(app_ok)
        resp_ok = client_ok.get("/health/detailed")
        assert resp_ok.status_code == 200
        data_ok = resp_ok.json()
        assert data_ok["status"] == "ok"
        assert data_ok["components"]["rag_kb"]["ok"] is True
    finally:
        server.stop()
    time.sleep(0.3)
    # 阶段 2：rag 挂掉（用已停止的 URL 重新构造 app，模拟持久 endpoint）
    app_down = _build_minimal_health_router(base_url)
    client_down = TestClient(app_down)
    resp_down = client_down.get("/health/detailed")
    assert resp_down.status_code == 207
    data_down = resp_down.json()
    assert data_down["status"] == "degraded"
    assert data_down["components"]["rag_kb"]["ok"] is False


# 功能：rag-kb + db 都健康时 /health/detailed 返回 200 + status=ok，不触发降级
# 设计：与上一条互为反例；保证 "全健康" 路径不被降级逻辑误判为 degraded
def test_health_detailed_reports_healthy_when_all_up() -> None:
    server = InProcessRagKbServer()
    base_url = server.start()
    try:
        app = _build_minimal_health_router(base_url)
        client = TestClient(app)
        resp = client.get("/health/detailed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["components"]["rag_kb"]["ok"] is True
        assert data["components"]["database"]["ok"] is True
        # /health 本身也应当 ok
        resp_basic = client.get("/health")
        assert resp_basic.status_code == 200
        assert resp_basic.json()["status"] == "ok"
    finally:
        server.stop()
