"""Trace Dashboard API 路由（agent: package-dashboard-api-v51）。

FastAPI 暴露 Dashboard 数据 API：
1. GET /api/dashboard/summary        — 全局总览（case 总数 / 成功率 / 平均延迟 / 总 Token / 总成本）
2. GET /api/dashboard/runs           — 评测运行列表（分页）
3. GET /api/dashboard/runs/{run_id}  — 单 run 详情
4. GET /api/dashboard/metrics/{run_id} — 单 run 的 7 指标
5. GET /api/dashboard/traces/{run_id} — 事件流（支持 case_id 过滤）

复用 `kivi_agent.eval.store.EvalResultStore` 持久化（`~/.kama/eval/results.jsonl`）。
对 WT-G1（EvalResult / EvalDataset）和 WT-G2（compute_all_metrics）的依赖**全部用懒导入**：
- dashboard 模块本身可在 WT-G1/G2 未合并时正常加载
- 端点用到时再 import；缺失时给出 501 / 明确错误
- 测试用 `monkeypatch` / `unittest.mock` 注入即可
"""

# src/kivi_agent/gateway/dashboard.py（agent: package-dashboard-api-v51）

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from kivi_agent.eval.store import EvalResultStore

log = logging.getLogger(__name__)


# 单例 store（agent: package-dashboard-api-v51）
_eval_store: EvalResultStore | None = None


def get_eval_store() -> EvalResultStore:
    """获取 EvalResultStore 单例（agent: package-dashboard-api-v51）。

    测试可通过 `dashboard._eval_store = EvalResultStore(tmp_path/...)` 注入。
    """
    global _eval_store
    if _eval_store is None:
        _eval_store = EvalResultStore()
    return _eval_store


def reset_eval_store_for_test() -> None:
    """重置单例（agent: package-dashboard-api-v51）。

    单元测试用 fixture 清理副作用；生产代码不应调用。
    """
    global _eval_store
    _eval_store = None


# 路径遍历保护：把 run_id 校验提取为公共工具（agent: package-dashboard-api-v51）
def _ensure_safe_run_id(run_id: str) -> None:
    """校验 run_id 安全（agent: package-dashboard-api-v51）。

    拒绝包含 `..` 的 run_id，防止路径遍历 / 越权访问。
    """
    if ".." in run_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid run_id",
        )


# 构造 dashboard router（agent: package-dashboard-api-v51）
def build_dashboard_router() -> APIRouter:
    """构造 dashboard APIRouter（agent: package-dashboard-api-v51）。"""
    router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

    @router.get("/summary")
    async def summary() -> dict[str, Any]:
        """全局总览（agent: package-dashboard-api-v51）。

        不依赖 metrics 模块（保持 WT-G3 独立）；简单聚合 token / 延迟 / 成功率。
        价格：input $0.003/1k, output $0.015/1k（与 metrics/cost.py 对齐）。
        """
        store = get_eval_store()
        all_results = list(store.iter_all())
        if not all_results:
            return {
                "case_count": 0,
                "success_rate": 0.0,
                "avg_latency_s": 0.0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }
        total = len(all_results)
        success = sum(1 for r in all_results if r.get("success"))
        # 延迟：每条结果取 started_at / finished_at 差值
        latencies: list[float] = []
        for r in all_results:
            t0, t1 = r.get("started_at"), r.get("finished_at")
            if t0 and t1:
                try:
                    dt0 = datetime.fromisoformat(t0)
                    dt1 = datetime.fromisoformat(t1)
                    latencies.append((dt1 - dt0).total_seconds())
                except (ValueError, TypeError):
                    pass
        # Token / 成本
        total_in = sum(r.get("input_tokens", 0) for r in all_results)
        total_out = sum(r.get("output_tokens", 0) for r in all_results)
        return {
            "case_count": total,
            "success_rate": success / total if total else 0.0,
            "avg_latency_s": sum(latencies) / len(latencies) if latencies else 0.0,
            "total_tokens": total_in + total_out,
            "total_cost_usd": round(
                (total_in / 1000) * 0.003 + (total_out / 1000) * 0.015, 4
            ),
        }

    @router.get("/runs")
    async def list_runs(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """评测运行列表（agent: package-dashboard-api-v51）。"""
        store = get_eval_store()
        runs = store.list_runs(limit=limit, offset=offset)
        return {"total": len(runs), "runs": runs}

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        """单 run 详情（agent: package-dashboard-api-v51）。"""
        _ensure_safe_run_id(run_id)
        store = get_eval_store()
        results = store.get_run(run_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run not found: {run_id}",
            )
        return {
            "run_id": run_id,
            "case_count": len(results),
            "success_count": sum(1 for r in results if r.get("success")),
            "results": results,
        }

    @router.get("/metrics/{run_id}")
    async def get_metrics(run_id: str) -> dict[str, Any]:
        """单 run 的 7 指标（agent: package-dashboard-api-v51）。

        懒导入 WT-G2 的 `compute_all_metrics`；WT-G1/G2 未合并时返回 501。
        """
        _ensure_safe_run_id(run_id)
        store = get_eval_store()
        results = store.get_run(run_id)
        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"run not found: {run_id}",
            )
        # 懒导入：依赖 WT-G1 (EvalCase/EvalDataset/EvalResult) + WT-G2 (compute_all_metrics)
        try:
            from kivi_agent.eval.dataset import EvalCase, EvalDataset
            from kivi_agent.eval.result import EvalResult
            from kivi_agent.eval.metrics.report import compute_all_metrics
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=f"metrics module not available: {exc}",
            ) from exc
        eval_results = [EvalResult.model_validate(r) for r in results]
        cases = [
            EvalCase(
                id=r.get("case_id", ""),
                goal=r.get("final_answer") or "(unknown)",
            )
            for r in results
        ]
        dataset = EvalDataset(name=run_id, cases=cases)
        report = compute_all_metrics(dataset, eval_results)
        result_dict: dict[str, Any] = report.to_dict()
        return result_dict

    @router.get("/traces/{run_id}")
    async def get_traces(
        run_id: str,
        case_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """单 run 的事件流（agent: package-dashboard-api-v51）。

        支持 `?case_id=xxx` 过滤单 case。
        """
        _ensure_safe_run_id(run_id)
        store = get_eval_store()
        results = store.get_run(run_id)
        if case_id is not None:
            results = [r for r in results if r.get("case_id") == case_id]
        return {
            "run_id": run_id,
            "trace_count": len(results),
            "traces": [
                {
                    "case_id": r.get("case_id"),
                    "events": r.get("events", []),
                    "tool_calls": r.get("tool_calls", []),
                    "rag_sources": r.get("rag_sources", []),
                }
                for r in results
            ],
        }

    return router


__all__ = [
    "build_dashboard_router",
    "get_eval_store",
    "reset_eval_store_for_test",
]
