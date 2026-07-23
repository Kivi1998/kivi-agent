"""T12 coding 8 指标（agent: package-eval-coding-v52）。

# coding.py（agent: package-eval-coding-v52）
8 指标（与 plan §二.2.3 对齐）：
- task_completion_rate: final_passed > 0 的 case 占比
- tests_passed_rate: Σ passed / Σ total（跨 case 累计）
- patch_quality: hunks_applied / hunks_proposed
- iteration_count: 平均每 case 循环轮次
- time_to_first_pass: first_pass_iteration 的平均值（归一化）
- self_recovery_rate: 失败→自愈次数 / 总失败次数
- compile_success_rate: pytest collect 通过（total > 0）的轮次占比
- test_growth_rate: Σ tests_added / Σ iterations

compute_all_coding_metrics: 一键汇总到 MetricsReport（复用 report.py 的）。
"""
from __future__ import annotations

from datetime import UTC, datetime

from kivi_agent.eval.coding.models import CodingEvalResult
from kivi_agent.eval.metrics.report import MetricsReport


# 1. 任务完成率：final_passed > 0 的 case 占比
def task_completion_rate(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算 final_passed > 0 的 case 占比。"""
    if not results:
        return {"rate": 0.0, "completed": 0, "total": 0}
    completed = sum(1 for r in results if r.final_passed > 0)
    return {
        "rate": completed / len(results),
        "completed": completed,
        "total": len(results),
    }


# 2. 测试通过率：Σ passed / Σ total
def tests_passed_rate(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算所有 case 的 passed / total 累计。"""
    total_passed = 0
    total_tests = 0
    for r in results:
        for tr in r.test_runs:
            total_passed += tr.passed
            total_tests += tr.total
    rate = total_passed / total_tests if total_tests else 0.0
    return {"rate": rate, "passed": total_passed, "total": total_tests}


# 3. patch 质量：hunks_applied / hunks_proposed
def patch_quality(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算所有 patch 的 hunk 应用率。"""
    total_proposed = 0
    total_applied = 0
    for r in results:
        for p in r.patches:
            total_proposed += p.hunk_count
            total_applied += p.applied_count
    rate = total_applied / total_proposed if total_proposed else 0.0
    return {
        "rate": rate,
        "applied": total_applied,
        "proposed": total_proposed,
    }


# 4. 循环轮次：每个 case 的 iteration_count 平均
def iteration_count(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算每 case 循环轮次的平均与最大。"""
    if not results:
        return {"avg": 0.0, "max": 0, "min": 0, "total": 0}
    counts = [r.iteration_count for r in results]
    return {
        "avg": sum(counts) / len(counts),
        "max": max(counts),
        "min": min(counts),
        "total": sum(counts),
    }


# 5. 首次通过时间：每个 case 的 first_pass_iteration 平均（归一化到 0-1）
def time_to_first_pass(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算 first_pass_iteration 的平均值与中位数。"""
    if not results:
        return {"avg": 0.0, "p50": 0, "max": 0, "never_passed": 0}
    firsts: list[int] = []
    never = 0
    for r in results:
        first = _first_pass_iter(r)
        if first is None:
            never += 1
        else:
            firsts.append(first)
    avg = sum(firsts) / len(firsts) if firsts else 0.0
    p50 = sorted(firsts)[len(firsts) // 2] if firsts else 0
    return {
        "avg": avg,
        "p50": p50,
        "max": max(firsts) if firsts else 0,
        "never_passed": never,
    }


# 6. 自愈率：自愈次数 / 总失败次数
def self_recovery_rate(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算 self_recovery_count / (失败轮次总数)。"""
    failures = 0
    for r in results:
        for tr in r.test_runs:
            if tr.passed < tr.total:
                failures += 1
    recoveries = sum(r.recovery_count for r in results)
    rate = recoveries / failures if failures else 0.0
    return {"rate": rate, "recoveries": recoveries, "failures": failures}


# 7. 编译/收集成功率：pytest collect 通过（total > 0）的轮次占比
def compile_success_rate(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算 pytest collect 成功（total > 0）的轮次占比。"""
    total_runs = 0
    success_runs = 0
    for r in results:
        for tr in r.test_runs:
            total_runs += 1
            if tr.total > 0:
                success_runs += 1
    rate = success_runs / total_runs if total_runs else 0.0
    return {
        "rate": rate,
        "success_runs": success_runs,
        "total_runs": total_runs,
    }


# 8. 测试增长：tests_added / iterations
def test_growth_rate(results: list[CodingEvalResult]) -> dict[str, float | int]:
    """计算每轮新增测试数的平均（pytest collect 数量变化）。"""
    total_added = 0
    total_iters = 0
    for r in results:
        for prev, cur in zip(r.test_runs, r.test_runs[1:]):
            total_added += max(0, cur.total - prev.total)
            total_iters += 1
    rate = total_added / total_iters if total_iters else 0.0
    return {
        "rate": rate,
        "tests_added": total_added,
        "iterations": total_iters,
    }


# 8 个指标的"规范顺序"（agent: package-eval-coding-v52）
CODING_METRIC_NAMES: tuple[str, ...] = (
    "task_completion_rate",
    "tests_passed_rate",
    "patch_quality",
    "iteration_count",
    "time_to_first_pass",
    "self_recovery_rate",
    "compile_success_rate",
    "test_growth_rate",
)


# 一键汇总 8 指标到 MetricsReport（agent: package-eval-coding-v52）
def compute_all_coding_metrics(
    results: list[CodingEvalResult],
    dataset_name: str = "coding",
) -> MetricsReport:
    """计算 8 个 T12 指标并组装 MetricsReport。"""
    metrics: dict[str, object] = {
        "task_completion_rate": task_completion_rate(results),
        "tests_passed_rate": tests_passed_rate(results),
        "patch_quality": patch_quality(results),
        "iteration_count": iteration_count(results),
        "time_to_first_pass": time_to_first_pass(results),
        "self_recovery_rate": self_recovery_rate(results),
        "compile_success_rate": compile_success_rate(results),
        "test_growth_rate": test_growth_rate(results),
    }
    return MetricsReport(
        dataset_name=dataset_name,
        case_count=len(results),
        metrics=metrics,
        generated_at=datetime.now(UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


# 找 case 的"首次通过" iter 序号（agent: package-eval-coding-v52）
def _first_pass_iter(result: CodingEvalResult) -> int | None:
    """返回首个 passed==total 且 total>0 的 iter；全失败返回 None。"""
    for tr in result.test_runs:
        if tr.passed == tr.total and tr.total > 0:
            return tr.iter
    return None
