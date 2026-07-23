"""Tool 选择正确率（agent: package-eval-metrics-v51）。"""
# tool_accuracy.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset  # type: ignore[import-not-found]
    from kivi_agent.eval.result import EvalResult  # type: ignore[import-not-found]

from kivi_agent.eval.metrics.base import Metric


class ToolAccuracyMetric(Metric):
    """Tool 选择正确率：实际 tool_calls 与 expected_tools 集合匹配度。"""

    name = "tool_selection_accuracy"
    description = "实际 tool_calls 与 expected_tools 集合匹配度（精确匹配 + 包含匹配）"

    # 计算 Tool 集合的精确匹配率与包含匹配率
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        case_map = {c.id: c for c in dataset.cases}
        exact_match = 0
        contain_match = 0
        applicable = 0
        for r in results:
            case = case_map.get(r.case_id)
            # 无 expected_tools 视为不适用（plan §二.2 指标公式不覆盖该 case）
            if case is None or not case.expected_tools:
                continue
            applicable += 1
            actual = {tc.tool_name for tc in r.tool_calls}
            expected = set(case.expected_tools)
            # 精确匹配：实际集合 == 期望集合（exact_match 同时计入 contain_match）
            if actual == expected:
                exact_match += 1
                contain_match += 1
            # 包含匹配：期望集合是实际集合的子集（多调了 Tool 仍算包含）
            elif expected.issubset(actual):
                contain_match += 1
        return {
            "exact_match_rate": exact_match / applicable if applicable else 0.0,
            "contain_match_rate": contain_match / applicable if applicable else 0.0,
            "applicable": applicable,
        }
