"""Team Dashboard API 路由（agent: package-dashboard-api-v52）。

FastAPI 暴露 Team 数据 API：
1. GET /api/team/summary                  — 团队总览（team 总数 / 成功率 / 平均协调延迟）
2. GET /api/team/teams                    — 团队列表（分页）
3. GET /api/team/teams/{team_id}          — 单 team 详情
4. GET /api/team/teams/{team_id}/delegations — 委派链
5. GET /api/team/teams/{team_id}/metrics  — T11 6 指标

复用 `kivi_agent.eval.team_store.TeamResultStore` 持久化（`~/.kama/eval/teams.jsonl`）。
对 H1（TeamEvalResult / TeamRunner / metrics.team）的依赖**全部用懒导入**：
- dashboard 模块本身可在 H1 未合并时正常加载
- 端点用到时再 import；缺失时给出 501 / 明确错误
- 测试用 `monkeypatch` / `unittest.mock` 注入即可
"""

# src/kivi_agent/gateway/team_dashboard.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, TypedDict, cast

from fastapi import APIRouter, HTTPException, Query, status

from kivi_agent.eval.team_store import TeamResultStore

log = logging.getLogger(__name__)


# 共享类型：TypedDict（agent: package-dashboard-api-v52）
# 设计：H1 会生产 `kivi_agent.eval.team.models.TeamEvalResult`；
# 集成期主控会把 TeamEvalResult 替入；本模块保持 dict-based 协议无强依赖。
class TeamSummary(TypedDict, total=False):
    """Team 列表摘要（agent: package-dashboard-api-v52）。"""

    team_id: str
    goal: str
    started_at: str | None
    member_count: int
    success: bool


class MemberOutcome(TypedDict, total=False):
    """Team 成员结果（agent: package-dashboard-api-v52）。"""

    name: str
    role: str
    success: bool
    steps: int
    finished_at: str | None


class DelegationStep(TypedDict, total=False):
    """委派步骤（agent: package-dashboard-api-v52）。"""

    from_member: str
    to_member: str
    topic: str
    ts: str


class TeamDetail(TypedDict, total=False):
    """Team 详情（agent: package-dashboard-api-v52）。"""

    team_id: str
    goal: str
    started_at: str | None
    finished_at: str | None
    success: bool
    member_count: int
    member_outcomes: list[MemberOutcome]
    delegations: list[DelegationStep]


# 单例 store（agent: package-dashboard-api-v52）
_team_store: TeamResultStore | None = None


def get_team_store() -> TeamResultStore:
    """获取 TeamResultStore 单例（agent: package-dashboard-api-v52）。

    测试可通过 `team_dashboard._team_store = TeamResultStore(tmp_path/...)` 注入。
    """
    global _team_store
    if _team_store is None:
        _team_store = TeamResultStore()
    return _team_store


def reset_team_store_for_test() -> None:
    """重置单例（agent: package-dashboard-api-v52）。

    单元测试用 fixture 清理副作用；生产代码不应调用。
    """
    global _team_store
    _team_store = None


# 路径遍历保护：把 team_id 校验提取为公共工具（agent: package-dashboard-api-v52）
def _ensure_safe_team_id(team_id: str) -> None:
    """校验 team_id 安全（agent: package-dashboard-api-v52）。

    拒绝包含 `..` 的 team_id，防止路径遍历 / 越权访问。
    """
    if ".." in team_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid team_id",
        )


# 从原始 dict 抽取 member outcome（agent: package-dashboard-api-v52）
def _extract_member_outcomes(row: dict[str, Any]) -> list[MemberOutcome]:
    """从 store 一行 dict 抽 member_outcomes；缺字段返回空列表。"""
    raw = row.get("member_outcomes")
    if isinstance(raw, list):
        return [cast(MemberOutcome, m) for m in raw if isinstance(m, dict)]
    return []


# 从原始 dict 抽取 delegations（agent: package-dashboard-api-v52）
def _extract_delegations(row: dict[str, Any]) -> list[DelegationStep]:
    """从 store 一行 dict 抽 delegations；缺字段返回空列表。"""
    raw = row.get("delegations")
    if isinstance(raw, list):
        return [cast(DelegationStep, d) for d in raw if isinstance(d, dict)]
    return []


# 构造 team dashboard router（agent: package-dashboard-api-v52）
def build_team_dashboard_router() -> APIRouter:
    """构造 team dashboard APIRouter（agent: package-dashboard-api-v52）。"""
    router = APIRouter(prefix="/api/team", tags=["team-dashboard"])

    @router.get("/summary")
    async def summary() -> dict[str, Any]:
        """Team 总览（agent: package-dashboard-api-v52）。

        不依赖 metrics 模块（保持 WT-H3 独立）；简单聚合成功率 / 平均协调延迟。
        协调延迟：每条 team 取 started_at / finished_at 差值的平均。
        """
        store = get_team_store()
        all_results = list(store.iter_all())
        # 去重 team_id（与 TeamResultStore.list_teams 行为一致）
        teams: dict[str, dict[str, Any]] = {}
        for r in all_results:
            tid = r.get("team_id")
            if not tid:
                continue
            existing = teams.get(tid)
            if existing is None:
                teams[tid] = r
            else:
                # 保留 started_at 较大者
                r_started = r.get("started_at") or ""
                e_started = existing.get("started_at") or ""
                if r_started > e_started:
                    teams[tid] = r
        if not teams:
            return {
                "team_count": 0,
                "success_rate": 0.0,
                "avg_coordination_latency_s": 0.0,
            }
        total = len(teams)
        success = sum(1 for t in teams.values() if t.get("success"))
        # 协调延迟：每条 team 取 started_at / finished_at 差值
        latencies: list[float] = []
        for t in teams.values():
            t0, t1 = t.get("started_at"), t.get("finished_at")
            if t0 and t1:
                try:
                    dt0 = datetime.fromisoformat(t0)
                    dt1 = datetime.fromisoformat(t1)
                    latencies.append((dt1 - dt0).total_seconds())
                except (ValueError, TypeError):
                    pass
        return {
            "team_count": total,
            "success_rate": success / total if total else 0.0,
            "avg_coordination_latency_s": (
                sum(latencies) / len(latencies) if latencies else 0.0
            ),
        }

    @router.get("/teams")
    async def list_teams(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Team 列表（agent: package-dashboard-api-v52）。"""
        store = get_team_store()
        teams = store.list_teams(limit=limit, offset=offset)
        return {"total": len(teams), "teams": teams}

    @router.get("/teams/{team_id}")
    async def get_team(team_id: str) -> dict[str, Any]:
        """单 team 详情（agent: package-dashboard-api-v52）。"""
        _ensure_safe_team_id(team_id)
        store = get_team_store()
        results = store.get_team(team_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"team not found: {team_id}",
            )
        # 取最新一行（按 started_at 倒序）
        latest = max(results, key=lambda r: r.get("started_at") or "")
        return {
            "team_id": team_id,
            "goal": latest.get("goal", ""),
            "started_at": latest.get("started_at"),
            "finished_at": latest.get("finished_at"),
            "success": bool(latest.get("success", False)),
            "member_count": latest.get("member_count", 0)
            or len(latest.get("member_specs", [])),
            "member_outcomes": _extract_member_outcomes(latest),
            "delegations": _extract_delegations(latest),
        }

    @router.get("/teams/{team_id}/delegations")
    async def get_team_delegations(team_id: str) -> dict[str, Any]:
        """Team 委派链（agent: package-dashboard-api-v52）。"""
        _ensure_safe_team_id(team_id)
        store = get_team_store()
        results = store.get_team(team_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"team not found: {team_id}",
            )
        latest = max(results, key=lambda r: r.get("started_at") or "")
        delegations = _extract_delegations(latest)
        return {
            "team_id": team_id,
            "delegation_count": len(delegations),
            "delegations": delegations,
        }

    @router.get("/teams/{team_id}/metrics")
    async def get_team_metrics(team_id: str) -> dict[str, Any]:
        """Team 的 T11 6 指标（agent: package-dashboard-api-v52）。

        懒导入 H1 的 `compute_team_metrics`；H1 未合并时返回 501。
        返回 6 指标：team_success_rate / delegation_accuracy / handoff_quality /
        coordination_latency / agent_utilization / role_consistency。
        """
        _ensure_safe_team_id(team_id)
        store = get_team_store()
        results = store.get_team(team_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"team not found: {team_id}",
            )
        # 懒导入：依赖 H1 (TeamEvalResult) + H1 metrics.team
        try:
            from kivi_agent.eval.metrics.team import compute_team_metrics  # type: ignore[import-not-found]
            from kivi_agent.eval.team.models import TeamEvalResult  # type: ignore[import-not-found]
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"team metrics module not available: {exc}",
            ) from exc
        team_results = [TeamEvalResult.model_validate(r) for r in results]
        # 取最新一行作为主结果（一个 team 通常对应一条结果）
        latest = max(team_results, key=lambda r: r.started_at or "")
        result_dict: dict[str, Any] = compute_team_metrics(latest)
        return result_dict

    return router


__all__ = [
    "DelegationStep",
    "MemberOutcome",
    "TeamDetail",
    "TeamSummary",
    "build_team_dashboard_router",
    "get_team_store",
    "reset_team_store_for_test",
]
