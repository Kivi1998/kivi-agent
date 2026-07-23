"""指标计算引擎（agent: package-eval-metrics-v51 + package-eval-metrics-v52）。"""
# __init__.py（agent: package-eval-metrics-v51 / v52）

from kivi_agent.eval.metrics.base import Metric
from kivi_agent.eval.metrics.cost import CostMetric
from kivi_agent.eval.metrics.latency import LatencyMetric
from kivi_agent.eval.metrics.rag_citation import RagCitationMetric
from kivi_agent.eval.metrics.report import MetricsReport, PricingTable, compute_all_metrics
from kivi_agent.eval.metrics.route_accuracy import RouteAccuracyMetric
from kivi_agent.eval.metrics.task_success import TaskSuccessMetric
from kivi_agent.eval.metrics.team import (
    TEAM_METRICS,
    AgentUtilizationMetric,
    CoordinationLatencyMetric,
    DelegationAccuracyMetric,
    HandoffQualityMetric,
    RoleConsistencyMetric,
    TeamMetric,
    TeamMetricsReport,
    TeamSuccessRateMetric,
    compute_all_team_metrics,
)
from kivi_agent.eval.metrics.token import TokenMetric
from kivi_agent.eval.metrics.tool_accuracy import ToolAccuracyMetric

__all__ = [
    # 基础（v51）
    "Metric",
    "TaskSuccessMetric",
    "RouteAccuracyMetric",
    "ToolAccuracyMetric",
    "RagCitationMetric",
    "LatencyMetric",
    "TokenMetric",
    "CostMetric",
    "MetricsReport",
    "PricingTable",
    "compute_all_metrics",
    # Team（v52 T11）
    "TEAM_METRICS",
    "TeamMetric",
    "TeamMetricsReport",
    "TeamSuccessRateMetric",
    "DelegationAccuracyMetric",
    "HandoffQualityMetric",
    "CoordinationLatencyMetric",
    "AgentUtilizationMetric",
    "RoleConsistencyMetric",
    "compute_all_team_metrics",
]
