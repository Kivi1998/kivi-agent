"""路由正确率（agent: package-eval-metrics-v51）。"""
# route_accuracy.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset  # type: ignore[import-not-found]
    from kivi_agent.eval.result import EvalResult  # type: ignore[import-not-found]

from kivi_agent.eval.metrics.base import Metric


class RouteAccuracyMetric(Metric):
    """路由正确率：RouteDecision.intent 命中 case.expected_route 的比例。"""

    name = "route_accuracy"
    description = "RouteDecision.intent == case.expected_route 的比例"

    # 计算有路由期望样本的意图匹配率
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        # 用 case_id 建索引避免 O(N) 线性查找
        case_map = {c.id: c for c in dataset.cases}
        matched = 0
        applicable = 0
        for r in results:
            case = case_map.get(r.case_id)
            # 三种情况跳过：case 缺失 / 无 expected_route / 无 route_decision
            if case is None or not case.expected_route or not r.route_decision:
                continue
            applicable += 1
            if r.route_decision.get("intent") == case.expected_route:
                matched += 1
        rate = matched / applicable if applicable else 0.0
        return {"rate": rate, "matched": matched, "applicable": applicable}
