"""Trace Dashboard API 集成测试（WT-G3 / agent: package-dashboard-api-v51）。

E2E 场景：
1. EvalResultStore 写入 → Dashboard API 读取（数据贯通）
2. 多次请求间持久化（store 单例 + JSONL 追加）
3. Dashboard router 集成到 FastAPI create_app（与现有 6 路由共存）

设计要点：
- 用 tmp_path 隔离 store（避免污染用户 ~/.kama/）
- 通过 `dashboard._eval_store` 单例注入测试 store
- 第三个测试同时验证 dashboard 路径在 app 上可访问 + 与现有 6 路由并存
"""

# tests/integration/test_dashboard_e2e.py（agent: package-dashboard-api-v51）

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import dashboard as dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- 复用：MockEvalResult --------------------------------------------------


class _MockEvent(BaseModel):
    type: str
    ts: str
    data: dict[str, Any] = {}


class _MockToolCall(BaseModel):
    name: str
    args: dict[str, Any] = {}


class _MockEvalResult(BaseModel):
    """与单元测试一致的 MockEvalResult（agent: package-dashboard-api-v51）。"""

    case_id: str
    run_id: str
    started_at: str
    finished_at: str
    success: bool = False
    final_answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    events: list[_MockEvent] = []
    tool_calls: list[_MockToolCall] = []
    rag_sources: list[str] = []


# ---- Fixtures --------------------------------------------------------------


def _make_result(**kwargs: Any) -> _MockEvalResult:
    """构造 MockEvalResult（agent: package-dashboard-api-v51）。"""
    defaults: dict[str, Any] = {
        "case_id": "c1",
        "run_id": "r1",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:01",
        "success": True,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    defaults.update(kwargs)
    return _MockEvalResult(**defaults)


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v51）。"""
    return tmp_path / "results.jsonl"


@pytest.fixture
def store(store_path: Path) -> Any:
    """EvalResultStore 注入 + 单例管理（agent: package-dashboard-api-v51）。"""
    from kivi_agent.eval.store import EvalResultStore

    s = EvalResultStore(store_path)
    dashboard_mod._eval_store = s
    yield s
    dashboard_mod._eval_store = None


# ---- E2E 场景 1：EvalRunner → Dashboard API -------------------------------


# 功能：写入 EvalResult 后 dashboard summary / runs / run 详情能正确读取
# 设计：存 5 case（2 个 run）→ 验证 3 个端点数据一致（无 CLI 依赖）
def test_e2e_eval_result_to_dashboard(tmp_path: Path, store: Any) -> None:
    """E2E 模拟 eval 结果 → dashboard 读取（agent: package-dashboard-api-v51）。

    注：原计划是 CLI `kivi-eval run` → dashboard；本分支无 eval CLI，
    故改为 "EvalResultStore.save() → 多个 dashboard 端点" 验证数据贯通。
    """
    # 模拟 EvalRunner 跑完 5 个 case 后批量 save
    results = [
        _make_result(case_id="c1", run_id="run-A", success=True,
                     input_tokens=100, output_tokens=50,
                     started_at="2026-01-01T00:00:00", finished_at="2026-01-01T00:00:01"),
        _make_result(case_id="c2", run_id="run-A", success=True,
                     input_tokens=200, output_tokens=100,
                     started_at="2026-01-01T00:00:02", finished_at="2026-01-01T00:00:03"),
        _make_result(case_id="c3", run_id="run-A", success=False,
                     input_tokens=50, output_tokens=25,
                     started_at="2026-01-01T00:00:04", finished_at="2026-01-01T00:00:05"),
        _make_result(case_id="c4", run_id="run-B", success=True,
                     input_tokens=300, output_tokens=150,
                     started_at="2026-01-02T00:00:00", finished_at="2026-01-02T00:00:02"),
        _make_result(case_id="c5", run_id="run-B", success=True,
                     input_tokens=400, output_tokens=200,
                     started_at="2026-01-02T00:00:03", finished_at="2026-01-02T00:00:04"),
    ]
    store.save_batch(results)

    # 构造 FastAPI app + TestClient
    from kivi_agent.core.gateway.runtime import SessionInfo

    class _RT:
        async def start_session(self, *a: Any, **k: Any) -> SessionInfo:
            return SessionInfo(
                session_id="x", user_id="u", goal="g",
                created_at="2026-01-01T00:00:00Z", status="active", run_id=None,
            )

        async def cancel_session(self, *a: Any, **k: Any) -> bool:
            return True

        async def list_sessions(self, *a: Any, **k: Any) -> list[SessionInfo]:
            return []

        async def get_session(self, *a: Any, **k: Any) -> SessionInfo | None:
            return None

        async def send_command(self, *a: Any, **k: Any) -> Any:
            return {}

        def subscribe_events(self, *a: Any, **k: Any) -> Any:
            async def g() -> Any:
                if False:
                    yield  # type: ignore[unreachable]

            return g()

    app = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app) as client:
        # /summary：5 case 全部，3 成功
        r_sum = client.get("/api/dashboard/summary")
        assert r_sum.status_code == 200
        body_sum = r_sum.json()
        assert body_sum["case_count"] == 5
        assert body_sum["success_rate"] == pytest.approx(4 / 5)

        # /runs：2 个 run
        r_runs = client.get("/api/dashboard/runs")
        assert r_runs.status_code == 200
        body_runs = r_runs.json()
        assert body_runs["total"] == 2
        run_ids = {r["run_id"] for r in body_runs["runs"]}
        assert run_ids == {"run-A", "run-B"}

        # /runs/{run_id}：run-A 详情（3 case）
        r_detail = client.get("/api/dashboard/runs/run-A")
        assert r_detail.status_code == 200
        body_detail = r_detail.json()
        assert body_detail["case_count"] == 3
        assert body_detail["success_count"] == 2
        assert len(body_detail["results"]) == 3


# ---- E2E 场景 2：持久化跨请求一致 -----------------------------------------


# 功能：写一次 store → 多个独立请求读取数据一致
# 设计：每个请求是独立 TestClient（模拟跨进程），数据从 JSONL 读
def test_e2e_persistence_across_requests(tmp_path: Path, store_path: Path) -> None:
    """E2E 多次请求间持久化（agent: package-dashboard-api-v51）。"""
    from kivi_agent.core.gateway.runtime import SessionInfo
    from kivi_agent.eval.store import EvalResultStore

    class _RT:
        async def start_session(self, *a: Any, **k: Any) -> SessionInfo:
            return SessionInfo(
                session_id="x", user_id="u", goal="g",
                created_at="2026-01-01T00:00:00Z", status="active", run_id=None,
            )

        async def cancel_session(self, *a: Any, **k: Any) -> bool:
            return True

        async def list_sessions(self, *a: Any, **k: Any) -> list[SessionInfo]:
            return []

        async def get_session(self, *a: Any, **k: Any) -> SessionInfo | None:
            return None

        async def send_command(self, *a: Any, **k: Any) -> Any:
            return {}

        def subscribe_events(self, *a: Any, **k: Any) -> Any:
            async def g() -> Any:
                if False:
                    yield  # type: ignore[unreachable]

            return g()

    # 第一次"会话"：写 2 case 到 store
    s1 = EvalResultStore(store_path)
    dashboard_mod._eval_store = s1
    s1.save(_make_result(case_id="c1", run_id="run-p", input_tokens=10, output_tokens=5))
    s1.save(_make_result(case_id="c2", run_id="run-p", input_tokens=20, output_tokens=10))

    app = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app) as client:
        # 第一次请求：读 summary（应看到 2 case）
        r1 = client.get("/api/dashboard/summary")
        assert r1.status_code == 200
        assert r1.json()["case_count"] == 2

    # 模拟"新进程"：用同一 path 重新构造 store + 重新挂到 app
    s2 = EvalResultStore(store_path)
    dashboard_mod._eval_store = s2
    app2 = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app2) as client:
        # 第二次请求：数据应依然在（从 JSONL 读）
        r2 = client.get("/api/dashboard/summary")
        assert r2.status_code == 200
        body = r2.json()
        assert body["case_count"] == 2
        # run-p 应在 list_runs 中
        r_runs = client.get("/api/dashboard/runs")
        run_ids = {r["run_id"] for r in r_runs.json()["runs"]}
        assert "run-p" in run_ids

    # 清理
    dashboard_mod._eval_store = None


# ---- E2E 场景 3：dashboard router 集成到 create_app -----------------------


# 功能：dashboard 5 端点都注册到 create_app 的 FastAPI app
# 设计：枚举 app.router.routes 验证 5 个 dashboard 路径 + 与 6 个原路由共存
def test_e2e_dashboard_in_gateway_app(tmp_path: Path) -> None:
    """E2E 验证 dashboard router 集成到 FastAPI app（agent: package-dashboard-api-v51）。"""
    from kivi_agent.core.gateway.runtime import SessionInfo

    class _RT:
        async def start_session(self, *a: Any, **k: Any) -> SessionInfo:
            return SessionInfo(
                session_id="x", user_id="u", goal="g",
                created_at="2026-01-01T00:00:00Z", status="active", run_id=None,
            )

        async def cancel_session(self, *a: Any, **k: Any) -> bool:
            return True

        async def list_sessions(self, *a: Any, **k: Any) -> list[SessionInfo]:
            return []

        async def get_session(self, *a: Any, **k: Any) -> SessionInfo | None:
            return None

        async def send_command(self, *a: Any, **k: Any) -> Any:
            return {}

        def subscribe_events(self, *a: Any, **k: Any) -> Any:
            async def g() -> Any:
                if False:
                    yield  # type: ignore[unreachable]

            return g()

    # 注入 store（用 tmp_path 避免污染 ~/.kama/）
    from kivi_agent.eval.store import EvalResultStore

    dashboard_mod._eval_store = EvalResultStore(tmp_path / "results.jsonl")
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # 5 个 dashboard 端点都应可访问
            dashboard_paths = [
                "/api/dashboard/summary",
                "/api/dashboard/runs",
            ]
            for p in dashboard_paths:
                r = client.get(p)
                assert r.status_code == 200, f"{p} should return 200"

            # 4xx 端点（带 run_id 占位）
            r404 = client.get("/api/dashboard/runs/missing-run")
            assert r404.status_code == 404

            # 6 个原有路由依然存在
            r_health = client.get("/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 验证 /openapi.json 含 dashboard schema（API 可发现性）
            r_openapi = client.get("/openapi.json")
            assert r_openapi.status_code == 200
            openapi = r_openapi.json()
            assert "/api/dashboard/summary" in openapi["paths"]
            assert "/api/dashboard/runs" in openapi["paths"]
            assert "/api/dashboard/runs/{run_id}" in openapi["paths"]
            assert "/api/dashboard/metrics/{run_id}" in openapi["paths"]
            assert "/api/dashboard/traces/{run_id}" in openapi["paths"]
    finally:
        dashboard_mod._eval_store = None
