"""任务成功率（agent: package-eval-metrics-v51）。"""
# task_success.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset  # type: ignore[import-not-found]
    from kivi_agent.eval.result import EvalResult  # type: ignore[import-not-found]

from kivi_agent.eval.metrics.base import Metric


class TaskSuccessMetric(Metric):
    """任务成功率：成功 case / 总 case（agent: package-eval-metrics-v51）。"""

    name = "task_success_rate"
    description = "成功 case / 总 case"

    # 计算任务成功率及通过数量
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        # 空结果短路返回，避免除零
        if not results:
            return {"rate": 0.0, "passed": 0, "total": 0}
        passed = sum(1 for r in results if r.success)
        return {
            "rate": passed / len(results),
            "passed": passed,
            "total": len(results),
        }
