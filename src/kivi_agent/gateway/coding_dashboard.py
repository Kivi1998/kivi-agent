"""Coding Dashboard API 路由（agent: package-dashboard-api-v52）。

FastAPI 暴露 Coding 数据 API：
1. GET /api/coding/summary               — Coding 总览（run 总数 / 完成率 / 平均迭代数）
2. GET /api/coding/runs                  — Coding 运行列表（分页）
3. GET /api/coding/runs/{run_id}         — 单 run 详情
4. GET /api/coding/runs/{run_id}/patches — patch 历史
5. GET /api/coding/runs/{run_id}/metrics — T12 8 指标

复用 `kivi_agent.eval.coding_store.CodingResultStore` 持久化（`~/.kama/eval/coding.jsonl`）。
对 H2（CodingEvalResult / CodingAgent / metrics.coding）的依赖**全部用懒导入**：
- dashboard 模块本身可在 H2 未合并时正常加载
- 端点用到时再 import；缺失时给出 501 / 明确错误
- 测试用 `monkeypatch` / `unittest.mock` 注入即可
"""

# src/kivi_agent/gateway/coding_dashboard.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, TypedDict, cast

from fastapi import APIRouter, HTTPException, Query, status

from kivi_agent.eval.coding_store import CodingResultStore

log = logging.getLogger(__name__)


# 共享类型：TypedDict（agent: package-dashboard-api-v52）
# 设计：H2 会生产 `kivi_agent.eval.coding.models.CodingEvalResult`；
# 集成期主控会把 CodingEvalResult 替入；本模块保持 dict-based 协议无强依赖。
class CodingSummary(TypedDict, total=False):
    """Coding run 列表摘要（agent: package-dashboard-api-v52）。"""

    run_id: str
    task: str
    started_at: str | None
    iterations: int
    completed: bool


class PatchRecord(TypedDict, total=False):
    """Patch 记录（agent: package-dashboard-api-v52）。"""

    iter: int
    file: str
    hunks_applied: int
    hunks_proposed: int
    ts: str | None


class TestRunRecord(TypedDict, total=False):
    """测试运行记录（agent: package-dashboard-api-v52）。"""

    iter: int
    passed: int
    total: int
    ts: str | None


class CodingDetail(TypedDict, total=False):
    """Coding run 详情（agent: package-dashboard-api-v52）。"""

    run_id: str
    task: str
    started_at: str | None
    finished_at: str | None
    completed: bool
    iterations: int
    patches: list[PatchRecord]
    test_runs: list[TestRunRecord]


# 单例 store（agent: package-dashboard-api-v52）
_coding_store: CodingResultStore | None = None


def get_coding_store() -> CodingResultStore:
    """获取 CodingResultStore 单例（agent: package-dashboard-api-v52）。

    测试可通过 `coding_dashboard._coding_store = CodingResultStore(tmp_path/...)` 注入。
    """
    global _coding_store
    if _coding_store is None:
        _coding_store = CodingResultStore()
    return _coding_store


def reset_coding_store_for_test() -> None:
    """重置单例（agent: package-dashboard-api-v52）。

    单元测试用 fixture 清理副作用；生产代码不应调用。
    """
    global _coding_store
    _coding_store = None


# 路径遍历保护：把 run_id 校验提取为公共工具（agent: package-dashboard-api-v52）
def _ensure_safe_run_id(run_id: str) -> None:
    """校验 run_id 安全（agent: package-dashboard-api-v52）。

    拒绝包含 `..` 的 run_id，防止路径遍历 / 越权访问。
    """
    if ".." in run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid run_id",
        )


# 从原始 dict 抽取 patches（agent: package-dashboard-api-v52）
def _extract_patches(row: dict[str, Any]) -> list[PatchRecord]:
    """从 store 一行 dict 抽 patches；缺字段返回空列表。"""
    raw = row.get("patches")
    if isinstance(raw, list):
        return [cast(PatchRecord, p) for p in raw if isinstance(p, dict)]
    return []


# 从原始 dict 抽取 test_runs（agent: package-dashboard-api-v52）
def _extract_test_runs(row: dict[str, Any]) -> list[TestRunRecord]:
    """从 store 一行 dict 抽 test_runs；缺字段返回空列表。"""
    raw = row.get("test_runs")
    if isinstance(raw, list):
        return [cast(TestRunRecord, t) for t in raw if isinstance(t, dict)]
    return []


# 构造 coding dashboard router（agent: package-dashboard-api-v52）
def build_coding_dashboard_router() -> APIRouter:
    """构造 coding dashboard APIRouter（agent: package-dashboard-api-v52）。"""
    router = APIRouter(prefix="/api/coding", tags=["coding-dashboard"])

    @router.get("/summary")
    async def summary() -> dict[str, Any]:
        """Coding 总览（agent: package-dashboard-api-v52）。

        不依赖 metrics 模块（保持 WT-H3 独立）；简单聚合完成率 / 平均迭代数。
        """
        store = get_coding_store()
        all_results = list(store.iter_all())
        # 去重 run_id（与 CodingResultStore.list_runs 行为一致）
        runs: dict[str, dict[str, Any]] = {}
        for r in all_results:
            rid = r.get("run_id")
            if not rid:
                continue
            existing = runs.get(rid)
            if existing is None:
                runs[rid] = r
            else:
                r_started = r.get("started_at") or ""
                e_started = existing.get("started_at") or ""
                if r_started > e_started:
                    runs[rid] = r
        if not runs:
            return {
                "run_count": 0,
                "completion_rate": 0.0,
                "avg_iterations": 0.0,
            }
        total = len(runs)
        completed = sum(
            1
            for r in runs.values()
            if r.get("completed", r.get("success", False))
        )
        iters = [
            r.get("iterations", 0) or r.get("iteration_count", 0) or 0
            for r in runs.values()
        ]
        return {
            "run_count": total,
            "completion_rate": completed / total if total else 0.0,
            "avg_iterations": sum(iters) / len(iters) if iters else 0.0,
        }

    @router.get("/runs")
    async def list_runs(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Coding 运行列表（agent: package-dashboard-api-v52）。"""
        store = get_coding_store()
        runs = store.list_runs(limit=limit, offset=offset)
        return {"total": len(runs), "runs": runs}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        """单 run 详情（agent: package-dashboard-api-v52）。"""
        _ensure_safe_run_id(run_id)
        store = get_coding_store()
        results = store.get_run(run_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run not found: {run_id}",
            )
        # 取最新一行
        latest = max(results, key=lambda r: r.get("started_at") or "")
        return {
            "run_id": run_id,
            "task": latest.get("task", ""),
            "started_at": latest.get("started_at"),
            "finished_at": latest.get("finished_at"),
            "completed": bool(latest.get("completed", latest.get("success", False))),
            "iterations": latest.get("iterations", 0)
            or latest.get("iteration_count", 0),
            "patches": _extract_patches(latest),
            "test_runs": _extract_test_runs(latest),
        }

    @router.get("/runs/{run_id}/patches")
    async def get_run_patches(run_id: str) -> dict[str, Any]:
        """Coding run 的 patch 历史（agent: package-dashboard-api-v52）。"""
        _ensure_safe_run_id(run_id)
        store = get_coding_store()
        results = store.get_run(run_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run not found: {run_id}",
            )
        latest = max(results, key=lambda r: r.get("started_at") or "")
        patches = _extract_patches(latest)
        return {
            "run_id": run_id,
            "patch_count": len(patches),
            "patches": patches,
        }

    @router.get("/runs/{run_id}/metrics")
    async def get_run_metrics(run_id: str) -> dict[str, Any]:
        """Coding run 的 T12 8 指标（agent: package-dashboard-api-v52）。

        懒导入 H2 的 `compute_coding_metrics`；H2 未合并时返回 501。
        返回 8 指标：task_completion_rate / tests_passed_rate / patch_quality /
        iteration_count / time_to_first_pass / self_recovery_rate / compile_success_rate /
        test_growth_rate。
        """
        _ensure_safe_run_id(run_id)
        store = get_coding_store()
        results = store.get_run(run_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run not found: {run_id}",
            )
        # 懒导入：依赖 H2 (CodingEvalResult) + H2 metrics.coding
        try:
            from kivi_agent.eval.coding.models import CodingEvalResult  # type: ignore[import-not-found]
            from kivi_agent.eval.metrics.coding import compute_coding_metrics  # type: ignore[import-not-found]
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"coding metrics module not available: {exc}",
            ) from exc
        coding_results = [CodingEvalResult.model_validate(r) for r in results]
        latest = max(coding_results, key=lambda r: r.started_at or "")
        result_dict: dict[str, Any] = compute_coding_metrics(latest)
        return result_dict

    return router


__all__ = [
    "CodingDetail",
    "CodingSummary",
    "PatchRecord",
    "TestRunRecord",
    "build_coding_dashboard_router",
    "get_coding_store",
    "reset_coding_store_for_test",
]
