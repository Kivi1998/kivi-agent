"""指标报告（agent: package-eval-metrics-v51）。"""
# report.py（agent: package-eval-metrics-v51）

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset
    from kivi_agent.eval.result import EvalResult

from kivi_agent.eval.metrics.base import Metric
from kivi_agent.eval.metrics.cost import CostMetric
from kivi_agent.eval.metrics.latency import LatencyMetric
from kivi_agent.eval.metrics.rag_citation import RagCitationMetric
from kivi_agent.eval.metrics.route_accuracy import RouteAccuracyMetric
from kivi_agent.eval.metrics.task_success import TaskSuccessMetric
from kivi_agent.eval.metrics.token import TokenMetric
from kivi_agent.eval.metrics.tool_accuracy import ToolAccuracyMetric


@dataclass
class MetricsReport:
    """指标报告（agent: package-eval-metrics-v51）。"""

    dataset_name: str
    case_count: int
    metrics: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    # 将指标报告转换为字典
    def to_dict(self) -> dict[str, Any]:
        """导出为 dict 便于 JSON 序列化。"""
        return asdict(self)

    # 将指标报告安全写入 JSON 文件
    def to_json(self, path: Path) -> None:
        # 路径遍历保护：拒绝包含 `..` 段的路径
        if ".." in path.parts:
            raise ValueError(f"invalid path: {path}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


# 价格表类型别名（与 CostMetric.pricing 对齐）
PricingTable = dict[str, tuple[float, float]]


# 计算全部七项指标并生成汇总报告
def compute_all_metrics(
    dataset: EvalDataset,
    results: list[EvalResult],
    pricing: PricingTable | None = None,
) -> MetricsReport:
    """计算所有 7 个指标并组装 MetricsReport（agent: package-eval-metrics-v51）。"""
    # 7 个指标实例按 plan §二.2 顺序排列：成功率 / 路由 / Tool / RAG / 延迟 / Token / 成本
    metrics_instances: list[Metric] = [
        TaskSuccessMetric(),
        RouteAccuracyMetric(),
        ToolAccuracyMetric(),
        RagCitationMetric(),
        LatencyMetric(),
        TokenMetric(),
        CostMetric(pricing=pricing),
    ]
    out: dict[str, Any] = {}
    for m in metrics_instances:
        # description 与各指标内字段合并为单 dict 写入 metrics
        out[m.name] = {"description": m.description, **m.compute(dataset, results)}
    return MetricsReport(
        dataset_name=dataset.name,
        case_count=len(dataset.cases),
        metrics=out,
        generated_at=datetime.now(UTC).isoformat(),
    )
