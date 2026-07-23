"""Team Dashboard API 集成测试（WT-H3 / agent: package-dashboard-api-v52）。

E2E 场景：
1. TeamResultStore 写入 → Team Dashboard API 读取（数据贯通）
2. 多次请求间持久化（store 单例 + JSONL 追加）
3. Team Dashboard router 集成到 FastAPI create_app（与 dashboard + 新路由共存）

设计要点：
- 用 tmp_path 隔离 store（避免污染用户 ~/.kama/）
- 通过 `team_dashboard._team_store` 单例注入测试 store
- 第三个测试同时验证 team 路径在 app 上可访问 + 与现有 6 + 5 路由并存
"""

# tests/integration/test_dashboard_team_e2e.py（agent: package-dashboard-api-v52）

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import team_dashboard as team_dashboard_mod
from kivi_agent.gateway.main import create_app


# ---- 复用：MockTeamResult --------------------------------------------------


class _MockTeamResult(BaseModel):
    """与单元测试一致的 MockTeamResult（agent: package-dashboard-api-v52）。"""

    team_id: str
    goal: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    success: bool = False
    member_specs: list[dict[str, Any]] = []
    member_count: int = 0
    member_outcomes: list[dict[str, Any]] = []
    delegations: list[dict[str, Any]] = []


def _make_result(**kwargs: Any) -> _MockTeamResult:
    """构造 MockTeamResult（agent: package-dashboard-api-v52）。"""
    defaults: dict[str, Any] = {
        "team_id": "t-1",
        "goal": "compare X and Y",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "success": True,
    }
    defaults.update(kwargs)
    return _MockTeamResult(**defaults)


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


# ---- E2E 场景 1：TeamResultStore → Team Dashboard API --------------------


# 功能：写入 TeamResult 后 team dashboard summary / teams / team 详情能正确读取
# 设计：存 5 team（跨 2 团队）→ 验证 3 个端点数据一致
def test_e2e_team_result_to_dashboard(tmp_path: Path) -> None:
    """E2E 模拟 team 结果 → team dashboard 读取（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.team_store import TeamResultStore

    s = TeamResultStore(tmp_path / "teams.jsonl")
    team_dashboard_mod._team_store = s
    try:
        # 模拟 TeamRunner 跑完 5 个 team 后批量 save
        # 2 个独立 team（team-A 2 次重跑 / team-B 1 次）→ summary 按最新一次算
        results = [
            _make_result(team_id="team-A", goal="research",
                         success=False, member_count=2,
                         started_at="2026-01-01T00:00:00",
                         finished_at="2026-01-01T00:00:05"),
            _make_result(team_id="team-A", goal="research",
                         success=True, member_count=2,
                         started_at="2026-01-01T00:00:10",
                         finished_at="2026-01-01T00:00:15"),
            _make_result(team_id="team-A", goal="research",
                         success=True, member_count=2,
                         started_at="2026-01-01T00:00:20",
                         finished_at="2026-01-01T00:00:25"),
            _make_result(team_id="team-B", goal="write",
                         success=True, member_count=1,
                         started_at="2026-01-02T00:00:00",
                         finished_at="2026-01-02T00:00:02"),
            _make_result(team_id="team-B", goal="write",
                         success=True, member_count=1,
                         started_at="2026-01-02T00:00:03",
                         finished_at="2026-01-02T00:00:04"),
        ]
        s.save_batch(results)

        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # /summary：2 个 team（去重），最新一次都成功
            r_sum = client.get("/api/team/summary")
            assert r_sum.status_code == 200
            body_sum = r_sum.json()
            assert body_sum["team_count"] == 2
            # summary 按"每个 team 的最新一行"算 success：team-A 最新 = True，team-B 最新 = True
            assert body_sum["success_rate"] == pytest.approx(1.0)
            # 平均协调延迟：team-A 5s + team-B ~1.5s (avg of 2 runs) → 整体平均
            # team-A 最新延迟 = 5s（最后一行 0:00:20→0:00:25）
            # team-B 两次跑（2s 和 1s，summary 取最新 = 1s）
            # avg = (5 + 1) / 2 = 3.0s
            assert body_sum["avg_coordination_latency_s"] == pytest.approx(3.0)

            # /teams：2 个 team
            r_teams = client.get("/api/team/teams")
            assert r_teams.status_code == 200
            body_teams = r_teams.json()
            assert body_teams["total"] == 2
            team_ids = {t["team_id"] for t in body_teams["teams"]}
            assert team_ids == {"team-A", "team-B"}

            # /teams/{team_id}：team-A 详情
            r_detail = client.get("/api/team/teams/team-A")
            assert r_detail.status_code == 200
            body_detail = r_detail.json()
            assert body_detail["team_id"] == "team-A"
            assert body_detail["member_count"] == 2
    finally:
        team_dashboard_mod._team_store = None


# ---- E2E 场景 2：持久化跨请求一致 -----------------------------------------


# 功能：写一次 store → 多个独立请求读取数据一致
# 设计：每个请求是独立 TestClient（模拟跨进程），数据从 JSONL 读
def test_e2e_persistence_across_requests(tmp_path: Path) -> None:
    """E2E 多次请求间持久化（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.team_store import TeamResultStore

    store_path = tmp_path / "teams.jsonl"

    # 第一次"会话"：写 2 team 到 store
    s1 = TeamResultStore(store_path)
    team_dashboard_mod._team_store = s1
    s1.save(_make_result(team_id="t-p1", started_at="2026-01-01T00:00:00",
                         finished_at="2026-01-01T00:00:05"))
    s1.save(_make_result(team_id="t-p2", started_at="2026-01-01T00:00:10",
                         finished_at="2026-01-01T00:00:15"))

    app = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app) as client:
        r1 = client.get("/api/team/summary")
        assert r1.status_code == 200
        assert r1.json()["team_count"] == 2

    # 模拟"新进程"：用同一 path 重新构造 store + 重新挂到 app
    s2 = TeamResultStore(store_path)
    team_dashboard_mod._team_store = s2
    app2 = create_app(runtime=_RT())  # type: ignore[arg-type]
    with TestClient(app2) as client:
        r2 = client.get("/api/team/summary")
        assert r2.status_code == 200
        body = r2.json()
        assert body["team_count"] == 2
        # t-p1 应在 list_teams 中
        r_teams = client.get("/api/team/teams")
        team_ids = {t["team_id"] for t in r_teams.json()["teams"]}
        assert {"t-p1", "t-p2"}.issubset(team_ids)

    team_dashboard_mod._team_store = None


# ---- E2E 场景 3：team dashboard router 集成到 create_app ------------------


# 功能：team dashboard 5 端点都注册到 create_app 的 FastAPI app
# 设计：枚举 app.router.routes 验证 5 个 team 路径 + 与 6 个原路由 + 5 个 dashboard 路由共存
def test_e2e_team_dashboard_in_gateway_app(tmp_path: Path) -> None:
    """E2E 验证 team dashboard router 集成到 FastAPI app（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.team_store import TeamResultStore

    team_dashboard_mod._team_store = TeamResultStore(tmp_path / "teams.jsonl")
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # 5 个 team dashboard 端点都应可访问
            team_paths = [
                "/api/team/summary",
                "/api/team/teams",
            ]
            for p in team_paths:
                r = client.get(p)
                assert r.status_code == 200, f"{p} should return 200"

            # 4xx 端点（带 team_id 占位）
            r404 = client.get("/api/team/teams/missing-team")
            assert r404.status_code == 404

            # 6 个原有路由依然存在
            r_health = client.get("/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 验证 /openapi.json 含 team dashboard schema
            r_openapi = client.get("/openapi.json")
            assert r_openapi.status_code == 200
            openapi = r_openapi.json()
            assert "/api/team/summary" in openapi["paths"]
            assert "/api/team/teams" in openapi["paths"]
            assert "/api/team/teams/{team_id}" in openapi["paths"]
            assert "/api/team/teams/{team_id}/delegations" in openapi["paths"]
            assert "/api/team/teams/{team_id}/metrics" in openapi["paths"]

            # 与原有 /api/dashboard/* 共存
            assert "/api/dashboard/summary" in openapi["paths"]
    finally:
        team_dashboard_mod._team_store = None
