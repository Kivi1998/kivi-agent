"""T11 6 个 team 协作指标（agent: package-eval-metrics-v52）。

# team.py（agent: package-eval-metrics-v52）
- TeamMetric 抽象基类：与 Wave 5.1 Metric 接口对齐但接收 list[TeamEvalResult]
- 6 个团队指标（plan §三 WT-H1 公式）：
  1. team_success_rate
  2. delegation_accuracy
  3. handoff_quality
  4. coordination_latency
  5. agent_utilization
  6. role_consistency
- TeamMetricsReport：汇总 + 路径遍历保护 to_json
- compute_all_team_metrics(results)：一键计算 6 指标
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kivi_agent.eval.team.models import TeamEvalResult


# team 指标抽象基类（agent: package-eval-metrics-v52）
class TeamMetric(ABC):
    """team 指标基类：compute 接收整个结果批次（plan §三 WT-H1 公式按批聚合）。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    # 聚合整批 TeamEvalResult 返回指标值
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        """聚合整批结果计算指标值；返回 {key: value} 字典。"""
        ...


# ---------------------------------------------------------------------------
# 1. team_success_rate
# ---------------------------------------------------------------------------


# 团队成功率：成功 team / 总 team
class TeamSuccessRateMetric(TeamMetric):
    """团队成功率：成功 team / 总 team。"""

    name = "team_success_rate"
    description = "成功 team / 总 team（success 由 member_outcomes 全部成功推出）"

    # 统计 success=True 的 team 比例
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        if not results:
            return {"rate": 0.0, "passed": 0, "total": 0}
        passed = sum(1 for r in results if r.success)
        return {
            "rate": passed / len(results),
            "passed": passed,
            "total": len(results),
        }


# ---------------------------------------------------------------------------
# 2. delegation_accuracy
# ---------------------------------------------------------------------------


# 委派准确性：actual 与 planned 重叠的委派数 / planned 总数
class DelegationAccuracyMetric(TeamMetric):
    """委派准确性：min(planned, actual) 总和 / planned 总和。"""

    name = "delegation_accuracy"
    description = "min(planned, actual) 总和 / planned 总和（按成员维度求和）"

    # 计算 plan vs actual 的命中率
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        if not results:
            return {"rate": 0.0, "matched": 0, "planned_total": 0}
        matched_total = 0
        planned_total = 0
        for r in results:
            planned = r.planned_assignments
            actual = r.actual_assignments
            planned_sum = sum(planned.values())
            planned_total += planned_sum
            if planned_sum == 0:
                continue
            # 按成员对齐：min(planned[m], actual.get(m, 0))
            overlap = sum(min(planned.get(m, 0), actual.get(m, 0)) for m in planned)
            matched_total += overlap
        return {
            "rate": matched_total / planned_total if planned_total else 0.0,
            "matched": matched_total,
            "planned_total": planned_total,
        }


# ---------------------------------------------------------------------------
# 3. handoff_quality
# ---------------------------------------------------------------------------


# Handoff 质量：成功消费消息 / 总消息
class HandoffQualityMetric(TeamMetric):
    """Handoff 质量：successful_messages / total_messages。"""

    name = "handoff_quality"
    description = "successful_messages / total_messages（mailbox 消费成功率）"

    # 汇总每个 team 的 handoff 比例
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        if not results:
            return {"rate": 0.0, "successful": 0, "total": 0}
        successful = 0
        total = 0
        for r in results:
            successful += r.successful_messages
            total += r.total_messages
        return {
            "rate": successful / total if total else 0.0,
            "successful": successful,
            "total": total,
        }


# ---------------------------------------------------------------------------
# 4. coordination_latency
# ---------------------------------------------------------------------------


# 协调延迟：finished_at - started_at 的平均与分位数
class CoordinationLatencyMetric(TeamMetric):
    """协调延迟：team.finished - team.created 平均与分位数。"""

    name = "coordination_latency_seconds"
    description = "team.finished.ts - team.created.ts 平均与分位数（秒）"

    # 解析 ISO 时间戳计算延迟
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        latencies: list[float] = []
        for r in results:
            if not r.started_at or not r.finished_at:
                continue
            try:
                t0 = datetime.fromisoformat(r.started_at)
                t1 = datetime.fromisoformat(r.finished_at)
                latencies.append((t1 - t0).total_seconds())
            except (ValueError, TypeError):
                continue
        if not latencies:
            return {"avg_s": 0.0, "p50_s": 0.0, "p95_s": 0.0, "count": 0}
        latencies.sort()
        n = len(latencies)
        return {
            "avg_s": sum(latencies) / n,
            "p50_s": latencies[n // 2],
            "p95_s": latencies[int(n * 0.95)] if n > 1 else latencies[0],
            "count": n,
        }


# ---------------------------------------------------------------------------
# 5. agent_utilization
# ---------------------------------------------------------------------------


# 智能体利用率：Σ tool_calls / (Σ steps × member_count)，上限 1.0
class AgentUtilizationMetric(TeamMetric):
    """智能体利用率：Σ tool_calls / (Σ steps × member_count)，上限 1.0。"""

    name = "agent_utilization"
    description = "Σ tool_calls / (Σ steps × member_count)，上限 1.0"

    # 汇总每个 team 的工具调用密度
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        if not results:
            return {"rate": 0.0, "tool_calls": 0, "step_x_member": 0}
        total_tool_calls = 0
        total_step_x_member = 0
        for r in results:
            members = r.member_outcomes
            if not members:
                continue
            team_tool = sum(m.tool_calls_count for m in members)
            team_steps = sum(m.steps for m in members)
            total_tool_calls += team_tool
            total_step_x_member += team_steps * len(members)
        rate = (
            total_tool_calls / total_step_x_member if total_step_x_member else 0.0
        )
        return {
            "rate": min(rate, 1.0),
            "raw_rate": rate,
            "tool_calls": total_tool_calls,
            "step_x_member": total_step_x_member,
        }


# ---------------------------------------------------------------------------
# 6. role_consistency
# ---------------------------------------------------------------------------


# 角色一致性：1 - role_changes / total_steps
class RoleConsistencyMetric(TeamMetric):
    """角色一致性：1 - role_changes / total_steps（无 role 变化时 = 1.0）。"""

    name = "role_consistency"
    description = "1 - role_changes / total_steps（0/0 时 = 1.0）"

    # 汇总每个 team 的角色稳定性
    def compute(self, results: list[TeamEvalResult]) -> dict[str, Any]:
        if not results:
            return {"rate": 1.0, "role_changes": 0, "total_steps": 0}
        total_role_changes = 0
        total_steps = 0
        for r in results:
            total_role_changes += r.role_changes
            total_steps += sum(m.steps for m in r.member_outcomes)
        if total_steps == 0:
            return {"rate": 1.0, "role_changes": total_role_changes, "total_steps": 0}
        rate = 1.0 - (total_role_changes / total_steps)
        return {
            "rate": max(0.0, min(1.0, rate)),
            "role_changes": total_role_changes,
            "total_steps": total_steps,
        }


# ---------------------------------------------------------------------------
# TeamMetricsReport + compute_all_team_metrics
# ---------------------------------------------------------------------------


# team 指标报告（agent: package-eval-metrics-v52）
@dataclass
class TeamMetricsReport:
    """team 指标报告。"""

    dataset_name: str
    team_count: int
    metrics: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""

    # 导出为 dict 便于 JSON 序列化
    def to_dict(self) -> dict[str, Any]:
        """导出为 dict。"""
        return asdict(self)

    # 写入 JSON 文件（含路径遍历保护）
    def to_json(self, path: Path) -> None:
        """写入 JSON 文件；路径段含 '..' 时拒绝。"""
        if ".." in path.parts:
            raise ValueError(f"invalid path: {path}")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)


# 6 个 team 指标实例（按 plan §三 WT-H1 顺序）
TEAM_METRICS: list[TeamMetric] = [
    TeamSuccessRateMetric(),
    DelegationAccuracyMetric(),
    HandoffQualityMetric(),
    CoordinationLatencyMetric(),
    AgentUtilizationMetric(),
    RoleConsistencyMetric(),
]


# 一键计算 6 个 team 指标并生成汇总报告
def compute_all_team_metrics(
    results: list[TeamEvalResult],
    *,
    dataset_name: str = "team_dataset",
) -> TeamMetricsReport:
    """计算 6 个 team 指标并组装 TeamMetricsReport。"""
    out: dict[str, Any] = {}
    for m in TEAM_METRICS:
        out[m.name] = {"description": m.description, **m.compute(results)}
    return TeamMetricsReport(
        dataset_name=dataset_name,
        team_count=len(results),
        metrics=out,
        generated_at=datetime.now(UTC).isoformat(),
    )
