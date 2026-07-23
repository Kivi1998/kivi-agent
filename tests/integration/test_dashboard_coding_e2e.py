"""Coding Dashboard API 集成测试（WT-H3 / agent: package-dashboard-api-v52）。

E2E 场景：
1. CodingResultStore 写入 → Coding Dashboard API 读取（数据贯通）
2. 多次请求间持久化（store 单例 + JSONL 追加）
3. Coding Dashboard router 集成到 FastAPI create_app（与 dashboard + team + coding 路由共存）

设计要点：
- 用 tmp_path 隔离 store（避免污染用户 ~/.kama/）
- 通过 `coding_dashboard._coding_store` 单例注入测试 store
- 第三个测试同时验证 coding 路径在 app 上可访问 + 与现有所有路由并存
"""

# tests/integration/test_dashboard_coding_e2e.py（agent: package-dashboard-api-v52）

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import coding_dashboard as coding_dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- 复用：MockCodingResult -----------------------------------------------


class _MockCodingResult(BaseModel):
    """与单元测试一致的 MockCodingResult（agent: package-dashboard-api-v52）。"""

    run_id: str
    task: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    completed: bool = False
    success: bool = False
    iterations: int = 0
    iteration_count: int = 0
    patches: list[dict[str, Any]] = []
    test_runs: list[dict[str, Any]] = []


def _make_result(**kwargs: Any) -> _MockCodingResult:
    """构造 MockCodingResult（agent: package-dashboard-api-v52）。"""
    defaults: dict[str, Any] = {
        "run_id": "r-1",
        "task": "Write add(a,b)",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "completed": True,
        "iterations": 2,
    }
    defaults.update(kwargs)
    return _MockCodingResult(**defaults)


class _RT:
    """FastAPI create_app 注入的 fake runtime。"""

    async def start_session(self, *a: Any, **k: Any) -> Any:
        from kivi_agent.core.gateway.runtime import SessionInfo

        return SessionInfo(
            session_id="x", user_id="u", goal="g",
            created_at="2026-01-01T00:00:00Z", status="active", run_id=None,
        )

    async def cancel_session(self, *a: Any, **k: Any) -> bool:
        return True

    async def list_sessions(self, *a: Any, **k: Any) -> list[Any]:
        return []

    async def get_session(self, *a: Any, **k: Any) -> Any:
        return None

    async def send_command(self, *a: Any, **k: Any) -> Any:
        return {}

    def subscribe_events(self, *a: Any, **k: Any) -> Any:
        async def g() -> Any:
            if False:
                yield  # type: ignore[unreachable]

        return g()


# ---- E2E 场景 1：CodingResultStore → Coding Dashboard API ----------------


# 功能：写入 CodingResult 后 coding dashboard summary / runs / run 详情能正确读取
# 设计：存 5 runs（跨 2 个编程任务）→ 验证 3 个端点数据一致
def test_e2e_coding_result_to_dashboard(tmp_path: Path) -> None:
    """E2E 模拟 coding 结果 → coding dashboard 读取（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.coding_store import CodingResultStore

    s = CodingResultStore(tmp_path / "coding.jsonl")
    coding_dashboard_mod._coding_store = s
    try:
        # 模拟 CodingAgent 跑完 5 个 case 后批量 save
        results = [
            _make_result(run_id="run-add", task="Write add",
                         completed=True, iterations=1,
                         started_at="2026-01-01T00:00:00",
                         finished_at="2026-01-01T00:00:05"),
            _make_result(run_id="run-add", task="Write add",
                         completed=True, iterations=2,
                         started_at="2026-01-01T00:00:10",
                         finished_at="2026-01-01T00:00:15"),
            _make_result(run_id="run-add", task="Write add",
                         completed=False, iterations=3,
                         started_at="2026-01-01T00:00:20",
                         finished_at="2026-01-01T00:00:25"),
            _make_result(run_id="run-fib", task="Write fibonacci",
                         completed=True, iterations=2,
                         started_at="2026-01-02T00:00:00",
                         finished_at="2026-01-02T00:00:02"),
            _make_result(run_id="run-fib", task="Write fibonacci",
                         completed=True, iterations=1,
                         started_at="2026-01-02T00:00:03",
                         finished_at="2026-01-02T00:00:04"),
        ]
        s.save_batch(results)

        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # /summary：2 个 run（去重）
            r_sum = client.get("/api/coding/summary")
            assert r_sum.status_code == 200
            body_sum = r_sum.json()
            assert body_sum["run_count"] == 2
            # 最新一次：run-add 失败 + run-fib 成功 = 1/2
            assert body_sum["completion_rate"] == pytest.approx(0.5)
            # avg_iterations = (3 + 1) / 2 = 2.0
            assert body_sum["avg_iterations"] == pytest.approx(2.0)

            # /runs：2 个 run
            r_runs = client.get("/api/coding/runs")
            assert r_runs.status_code == 200
            body_runs = r_runs.json()
            assert body_runs["total"] == 2
            run_ids = {r["run_id"] for r in body_runs["runs"]}
            assert run_ids == {"run-add", "run-fib"}

            # /runs/{run_id}：run-add 详情（取最新一行）
            r_detail = client.get("/api/coding/runs/run-add")
            assert r_detail.status_code == 200
            body_detail = r_detail.json()
            assert body_detail["run_id"] == "run-add"
            assert body_detail["iterations"] == 3  # 最新一行
            assert body_detail["completed"] is False  # 最新一行失败
    finally:
        coding_dashboard_mod._coding_store = None


# ---- E2E 场景 2：持久化跨请求一致 -----------------------------------------


# 功能：写一次 store → 多个独立请求读取数据一致
# 设计：每个请求是独立 TestClient（模拟跨进程），数据从 JSONL 读
def test_e2e_persistence_across_requests(tmp_path: Path) -> None:
    """E2E 多次请求间持久化（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.coding_store import CodingResultStore

    store_path = tmp_path / "coding.jsonl"

    # 第一次"会话"：写 2 runs 到 store
    s1 = CodingResultStore(store_path)
    coding_dashboard_mod._coding_store = s1
    s1.save(_make_result(run_id="r-p1", iterations=2))
    s1.save(_make_result(run_id="r-p2", iterations=3))

    app = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app) as client:
        r1 = client.get("/api/coding/summary")
        assert r1.status_code == 200
        assert r1.json()["run_count"] == 2

    # 模拟"新进程"
    s2 = CodingResultStore(store_path)
    coding_dashboard_mod._coding_store = s2
    app2 = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app2) as client:
        r2 = client.get("/api/coding/summary")
        assert r2.status_code == 200
        body = r2.json()
        assert body["run_count"] == 2
        # r-p1 应在 list_runs 中
        r_runs = client.get("/api/coding/runs")
        run_ids = {r["run_id"] for r in r_runs.json()["runs"]}
        assert {"r-p1", "r-p2"}.issubset(run_ids)

    coding_dashboard_mod._coding_store = None


# ---- E2E 场景 3：coding dashboard router 集成到 create_app ------------------


# 功能：coding dashboard 5 端点都注册到 create_app 的 FastAPI app
# 设计：枚举 app.router.routes 验证 5 个 coding 路径 + 与 6 个原路由 + dashboard + team 共存
def test_e2e_coding_dashboard_in_gateway_app(tmp_path: Path) -> None:
    """E2E 验证 coding dashboard router 集成到 FastAPI app（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.coding_store import CodingResultStore

    coding_dashboard_mod._coding_store = CodingResultStore(tmp_path / "coding.jsonl")
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # 5 个 coding dashboard 端点都应可访问
            coding_paths = [
                "/api/coding/summary",
                "/api/coding/runs",
            ]
            for p in coding_paths:
                r = client.get(p)
                assert r.status_code == 200, f"{p} should return 200"

            # 4xx 端点（带 run_id 占位）
            r404 = client.get("/api/coding/runs/missing-run")
            assert r404.status_code == 404

            # 6 个原有路由依然存在
            r_health = client.get("/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 验证 /openapi.json 含 coding dashboard schema
            r_openapi = client.get("/openapi.json")
            assert r_openapi.status_code == 200
            openapi = r_openapi.json()
            assert "/api/coding/summary" in openapi["paths"]
            assert "/api/coding/runs" in openapi["paths"]
            assert "/api/coding/runs/{run_id}" in openapi["paths"]
            assert "/api/coding/runs/{run_id}/patches" in openapi["paths"]
            assert "/api/coding/runs/{run_id}/metrics" in openapi["paths"]

            # 与原有 /api/dashboard/* + /api/team/* 共存
            assert "/api/dashboard/summary" in openapi["paths"]
            assert "/api/team/summary" in openapi["paths"]
    finally:
        coding_dashboard_mod._coding_store = None
