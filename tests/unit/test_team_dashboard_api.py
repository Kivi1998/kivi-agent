"""Team Dashboard API 单元测试（WT-H3 / agent: package-dashboard-api-v52）。

测试目标：
1. 5 个端点的请求/响应 schema
2. TeamResultStore JSONL 持久化（追加写 / 读取 / list_teams 分组）
3. 路径遍历保护（`..` in team_id → 400）
4. metrics 端点用 mock 注入（H1 模块当前不可用，测 handler 行为）
5. _ensure_safe_team_id / summary / 各种 200 / 404 场景

设计要点：
- 用 `team_dashboard.reset_team_store_for_test()` 隔离单例 + tmp_path 注入 store
- 用 `Pydantic BaseModel` 模拟 TeamResult
- 不依赖 H1 (TeamEvalResult/TeamRunner/metrics.team) 的实现
"""

# tests/unit/test_team_dashboard_api.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import team_dashboard as team_dashboard_mod
from kivi_agent.gateway.main import create_app


# ---- Mock 数据模型 ---------------------------------------------------------


class _MockTeamResult(BaseModel):
    """Mock TeamResult（H1 TeamEvalResult 的最小替代）。"""

    team_id: str
    goal: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    success: bool = False
    member_specs: list[dict[str, Any]] = []
    member_count: int = 0
    member_outcomes: list[dict[str, Any]] = []
    delegations: list[dict[str, Any]] = []


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v52）。"""
    return tmp_path / "teams.jsonl"


@pytest.fixture
def patch_store(store_path: Path):
    """注入临时 TeamResultStore + 清理单例（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.team_store import TeamResultStore

    store = TeamResultStore(store_path)
    team_dashboard_mod._team_store = store
    yield store
    team_dashboard_mod._team_store = None


class _FakeRuntime:
    """FastAPI create_app 注入的 fake runtime。"""

    async def start_session(self, *args: Any, **kwargs: Any) -> Any:
        from kivi_agent.core.gateway.runtime import SessionInfo

        return SessionInfo(
            session_id="x",
            user_id="u",
            goal="g",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id=None,
        )

    async def cancel_session(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def list_sessions(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def get_session(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def send_command(self, *args: Any, **kwargs: Any) -> Any:
        return {}

    def subscribe_events(self, *args: Any, **kwargs: Any) -> Any:
        async def _gen() -> Any:
            if False:
                yield  # type: ignore[unreachable]

        return _gen()


@pytest.fixture
def client(patch_store: Any) -> TestClient:
    """FastAPI TestClient + team store 注入（agent: package-dashboard-api-v52）。"""
    app = create_app(runtime=_FakeRuntime())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


# ---- 工具函数 --------------------------------------------------------------


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


# ---- /summary 端点测试 -----------------------------------------------------


# 功能：summary 在无数据时返回全 0 占位
# 设计：fresh store → team_count=0, success_rate=0.0, avg_coordination_latency_s=0.0
def test_summary_empty(client: TestClient) -> None:
    resp = client.get("/api/team/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "team_count": 0,
        "success_rate": 0.0,
        "avg_coordination_latency_s": 0.0,
    }


# 功能：summary 在有 3 team 时计算 success_rate / avg_coordination_latency_s
# 设计：3 条 team result 写入 store（2 成功 / 1 失败），断言比例 + 5s 延迟平均
def test_summary_with_teams(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result(team_id="t-1", success=True,
                                  started_at="2026-01-01T00:00:00",
                                  finished_at="2026-01-01T00:00:05"))
    patch_store.save(_make_result(team_id="t-2", success=True,
                                  started_at="2026-01-01T00:00:10",
                                  finished_at="2026-01-01T00:00:15"))
    patch_store.save(_make_result(team_id="t-3", success=False,
                                  started_at="2026-01-01T00:00:20",
                                  finished_at="2026-01-01T00:00:25"))

    resp = client.get("/api/team/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_count"] == 3
    assert body["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert body["avg_coordination_latency_s"] == pytest.approx(5.0)


# ---- /teams 端点测试 -------------------------------------------------------


# 功能：teams 端点按 limit/offset 分页返回 team 摘要
# 设计：3 个 team 各 1 case，验证 list_teams 按 started_at 倒序
def test_list_teams_default(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result(team_id="t-1", started_at="2026-01-01T00:00:00",
                                  finished_at="2026-01-01T00:00:05"))
    patch_store.save(_make_result(team_id="t-2", started_at="2026-01-03T00:00:00",
                                  finished_at="2026-01-03T00:00:05"))
    patch_store.save(_make_result(team_id="t-3", started_at="2026-01-02T00:00:00",
                                  finished_at="2026-01-02T00:00:05"))

    resp = client.get("/api/team/teams")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    team_ids = [r["team_id"] for r in body["teams"]]
    assert team_ids == ["t-2", "t-3", "t-1"]


# ---- /teams/{team_id} 端点测试 ---------------------------------------------


# 功能：teams/{team_id} 不存在时返回 404
# 设计：空 store + 随机 team_id → 404 + detail 含 team_id
def test_get_team_not_found(client: TestClient) -> None:
    resp = client.get("/api/team/teams/missing-team")
    assert resp.status_code == 404
    assert "missing-team" in resp.json()["detail"]


# 功能：teams/{team_id} 存在时返回完整 team 详情
# 设计：写入 1 team → 验证 member_outcomes / delegations 都返回
def test_get_team_detail(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockTeamResult(
            team_id="t-detail",
            goal="do thing",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T00:00:05",
            success=True,
            member_count=2,
            member_specs=[{"name": "r"}, {"name": "w"}],
            member_outcomes=[{"name": "r", "role": "research", "success": True}],
            delegations=[{"from_member": "r", "to_member": "w", "topic": "summary"}],
        )
    )
    resp = client.get("/api/team/teams/t-detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == "t-detail"
    assert body["member_count"] == 2
    assert len(body["member_outcomes"]) == 1
    assert len(body["delegations"]) == 1


# ---- /teams/{team_id}/delegations 端点测试 ---------------------------------


# 功能：delegations 端点只返回 delegations 字段
# 设计：写入 1 team 带 delegations → 验证 delegation_count + delegations
def test_get_team_delegations(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockTeamResult(
            team_id="t-del",
            delegations=[
                {"from_member": "a", "to_member": "b", "topic": "x"},
                {"from_member": "b", "to_member": "c", "topic": "y"},
            ],
        )
    )
    resp = client.get("/api/team/teams/t-del/delegations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == "t-del"
    assert body["delegation_count"] == 2
    assert len(body["delegations"]) == 2
    assert body["delegations"][0]["from_member"] == "a"


# 功能：delegations 端点 team 不存在时返回 404
# 设计：空 store → 404
def test_get_team_delegations_not_found(client: TestClient) -> None:
    resp = client.get("/api/team/teams/missing/delegations")
    assert resp.status_code == 404


# ---- /teams/{team_id}/metrics 端点测试 -------------------------------------


# 功能：metrics 端点调用 H1 compute_team_metrics 并返回 6 指标
# 设计：mock compute_team_metrics + TeamEvalResult 避免依赖未合并模块
def test_get_team_metrics_6_indicators(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockTeamResult(
            team_id="t-m",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T00:00:05",
        )
    )

    fake_metrics = {
        "team_success_rate": 0.8,
        "delegation_accuracy": 0.9,
        "handoff_quality": 0.7,
        "coordination_latency": 5.0,
        "agent_utilization": 0.6,
        "role_consistency": 0.95,
    }

    # 模拟 H1 模块不存在
    fake_team_pkg = types.ModuleType("kivi_agent.eval.team")
    fake_team_models = types.ModuleType("kivi_agent.eval.team.models")
    fake_metrics_pkg = types.ModuleType("kivi_agent.eval.metrics")
    fake_metrics_team = types.ModuleType("kivi_agent.eval.metrics.team")

    class _FakeTeamEvalResult(BaseModel):
        team_id: str
        started_at: str | None = None
        finished_at: str | None = None
        success: bool = False
        member_outcomes: list[Any] = []
        delegations: list[Any] = []

    fake_team_models.TeamEvalResult = _FakeTeamEvalResult  # type: ignore[attr-defined]
    fake_metrics_team.compute_team_metrics = lambda _r: fake_metrics  # type: ignore[attr-defined]

    with patch.dict(
        sys.modules,
        {
            "kivi_agent.eval.team": fake_team_pkg,
            "kivi_agent.eval.team.models": fake_team_models,
            "kivi_agent.eval.metrics": fake_metrics_pkg,
            "kivi_agent.eval.metrics.team": fake_metrics_team,
        },
    ):
        resp = client.get("/api/team/teams/t-m/metrics")

    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {
        "team_success_rate",
        "delegation_accuracy",
        "handoff_quality",
        "coordination_latency",
        "agent_utilization",
        "role_consistency",
    }
    assert expected_keys.issubset(body.keys())
    assert body["team_success_rate"] == 0.8


# 功能：metrics 端点在 H1 未合并时返回 501
# 设计：清空 sys.modules 的 team 让 lazy import 失败 → HTTPException 501
def test_get_team_metrics_501_when_modules_missing(
    client: TestClient, patch_store: Any
) -> None:
    patch_store.save(_MockTeamResult(team_id="t-x"))

    with patch.dict(
        sys.modules,
        {
            "kivi_agent.eval.team": None,
            "kivi_agent.eval.team.models": None,
            "kivi_agent.eval.metrics": None,
            "kivi_agent.eval.metrics.team": None,
        },
    ):
        resp = client.get("/api/team/teams/t-x/metrics")

    assert resp.status_code == 501
    assert "not available" in resp.json()["detail"]


# ---- 路径遍历保护测试 -----------------------------------------------------


# 功能：team_id 含 `..` 时返回 400（路径遍历保护）
# 设计：覆盖 3 个动态路由
def test_path_traversal_team_id(client: TestClient) -> None:
    r1 = client.get("/api/team/teams/..bad..")
    assert r1.status_code == 400
    r2 = client.get("/api/team/teams/..t../delegations")
    assert r2.status_code == 400
    r3 = client.get("/api/team/teams/foo..bar..baz/metrics")
    assert r3.status_code == 400
    assert "invalid team_id" in r1.json()["detail"]


# ---- 单例管理测试 ---------------------------------------------------------


# 功能：reset_team_store_for_test 后再 get_team_store 会重建单例
# 设计：set → reset → 重新 get 返回新实例（用 default 路径）
def test_reset_team_store_for_test() -> None:
    from kivi_agent.eval.team_store import TeamResultStore

    custom = TeamResultStore(Path("/tmp/test_reset_team.jsonl"))
    team_dashboard_mod._team_store = custom
    assert team_dashboard_mod.get_team_store() is custom
    team_dashboard_mod.reset_team_store_for_test()
    # reset 后：get_team_store 会创建默认实例
    default = team_dashboard_mod.get_team_store()
    assert default is not custom
    # 清理
    team_dashboard_mod.reset_team_store_for_test()
