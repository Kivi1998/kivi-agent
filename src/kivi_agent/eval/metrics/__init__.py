"""指标计算引擎（agent: package-eval-metrics-v51 + package-eval-metrics-v52）。"""
# __init__.py（agent: package-eval-metrics-v51 / v52）

from kivi_agent.eval.metrics.base import Metric
from kivi_agent.eval.metrics.coding import (
    CODING_METRIC_NAMES,
    compile_success_rate,
    compute_all_coding_metrics,
    growth_rate,
    iteration_count,
    patch_quality,
    self_recovery_rate,
    task_completion_rate,
    tests_passed_rate,
    time_to_first_pass,
)
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

# 公共 API 别名：plan §二.2.3 用 test_growth_rate 作 metric name；函数实现为 growth_rate
test_growth_rate = growth_rate

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
    # Coding（v52 T12）
    "CODING_METRIC_NAMES",
    "task_completion_rate",
    "tests_passed_rate",
    "patch_quality",
    "iteration_count",
    "time_to_first_pass",
    "self_recovery_rate",
    "compile_success_rate",
    "test_growth_rate",
    "compute_all_coding_metrics",
]
