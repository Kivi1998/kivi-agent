"""RAG 引用准确率（agent: package-eval-metrics-v51）。"""
# rag_citation.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset
    from kivi_agent.eval.result import EvalResult

from kivi_agent.eval.metrics.base import Metric


class RagCitationMetric(Metric):
    """RAG 引用准确率：实际 rag_sources.id 与 expected_sources 集合匹配度。"""

    name = "rag_citation_accuracy"
    description = "实际 rag_sources.id 与 expected_sources 集合匹配度"

    # 计算期望 RAG 引用集合的包含匹配率
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        case_map = {c.id: c for c in dataset.cases}
        matched = 0
        applicable = 0
        for r in results:
            case = case_map.get(r.case_id)
            # 无 expected_sources 视为不适用（无 RAG 期望则不评分）
            if case is None or not case.expected_sources:
                continue
            applicable += 1
            # rag_sources 是 dict 列表（Wave 1 RagSourcesCitedEvent 的 payload 形态）
            actual = {s.get("id") for s in r.rag_sources}
            expected = set(case.expected_sources)
            # 包含匹配：期望的引用必须全部出现在实际引用中（多引用不扣分）
            if expected.issubset(actual):
                matched += 1
        rate = matched / applicable if applicable else 0.0
        return {"rate": rate, "matched": matched, "applicable": applicable}
