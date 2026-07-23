"""T12 8 指标单元测试（agent: package-eval-coding-v52）。

# test_metrics_coding.py（agent: package-eval-coding-v52）
8 指标 × 3 fixture ≈ 24+ case：
- task_completion_rate: 全过 / 全败 / 混合 / 空
- tests_passed_rate: 全过 / 全败 / 混合
- patch_quality: 全应用 / 全失败 / 混合
- iteration_count: 单 case / 多 case
- time_to_first_pass: 全过 / 部分过 / 全败
- self_recovery_rate: 全自愈 / 全不愈 / 混合
- compile_success_rate: pytest collect 成功 vs 失败
- test_growth_rate: 测试数增长 / 持平 / 下降
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kivi_agent.eval.coding.models import (
    CodingCase,
    CodingEvalResult,
    PatchRecord,
    TestRunRecord,
)
from kivi_agent.eval.metrics.coding import (
    CODING_METRIC_NAMES,
    MetricsReport,
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


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


# 构造一个 CodingEvalResult 测试 fixture
def _result(
    case_id: str = "c1",
    *,
    final_passed: int = 0,
    iteration_count_: int = 1,
    success: bool = False,
    recovery_count: int = 0,
    test_runs: list[TestRunRecord] | None = None,
    patches: list[PatchRecord] | None = None,
) -> CodingEvalResult:
    """构造一个 CodingEvalResult 测试 fixture。"""
    return CodingEvalResult(
        case_id=case_id,
        iteration_count=iteration_count_,
        final_passed=final_passed,
        success=success,
        recovery_count=recovery_count,
        test_runs=test_runs or [],
        patches=patches or [],
    )


# 工厂：单 TestRunRecord
def _tr(iter: int, passed: int, total: int) -> TestRunRecord:
    return TestRunRecord(iter=iter, passed=passed, total=total, duration_seconds=0.1, output="")


# 工厂：单 PatchRecord
def _pr(iter: int, hunk_count: int = 1, applied_count: int = 1) -> PatchRecord:
    return PatchRecord(iter=iter, hunk_count=hunk_count, applied_count=applied_count, diff_text="")


# ---------------------------------------------------------------------------
# 1. task_completion_rate
# ---------------------------------------------------------------------------


# 功能：final_passed > 0 的 case 占比；全过 → 1.0
# 设计：3 个 case 全 final_passed=1 → 1.0 / 3 / 3
def test_task_completion_all_pass() -> None:
    results = [
        _result("c1", final_passed=1),
        _result("c2", final_passed=2),
        _result("c3", final_passed=1),
    ]
    out = task_completion_rate(results)
    assert out == {"rate": 1.0, "completed": 3, "total": 3}


# 功能：全败 → 0.0
# 设计：3 个 case 全 final_passed=0 → 0.0 / 0 / 3
def test_task_completion_all_fail() -> None:
    results = [_result(f"c{i}", final_passed=0) for i in range(3)]
    out = task_completion_rate(results)
    assert out == {"rate": 0.0, "completed": 0, "total": 3}


# 功能：混合 → 1/3 完成
# 设计：3 个 case 1 通过 2 失败 → 1/3
def test_task_completion_mixed() -> None:
    results = [
        _result("c1", final_passed=1),
        _result("c2", final_passed=0),
        _result("c3", final_passed=0),
    ]
    out = task_completion_rate(results)
    assert out["rate"] == pytest.approx(1 / 3)
    assert out["completed"] == 1


# 功能：空 results 短路返回 0.0 / 0 / 0
# 设计：直接传 [] → 0.0
def test_task_completion_empty() -> None:
    out = task_completion_rate([])
    assert out == {"rate": 0.0, "completed": 0, "total": 0}


# ---------------------------------------------------------------------------
# 2. tests_passed_rate
# ---------------------------------------------------------------------------


# 功能：全过率 1.0
# 设计：单 case 1 test run 5/5 → 1.0 / 5 / 5
def test_passed_rate_all_pass() -> None:
    results = [_result("c1", test_runs=[_tr(1, 5, 5)])]
    out = tests_passed_rate(results)
    assert out == {"rate": 1.0, "passed": 5, "total": 5}


# 功能：跨 case 累计 passed / total
# 设计：2 case 各 1 test run（3/5 + 4/4）→ 7/9
def test_passed_rate_accumulates() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 3, 5)]),
        _result("c2", test_runs=[_tr(1, 4, 4)]),
    ]
    out = tests_passed_rate(results)
    assert out["passed"] == 7
    assert out["total"] == 9
    assert out["rate"] == pytest.approx(7 / 9)


# 功能：全败 → 0.0
# 设计：单 case 1 test run 0/5 → 0.0
def test_passed_rate_all_fail() -> None:
    results = [_result("c1", test_runs=[_tr(1, 0, 5)])]
    out = tests_passed_rate(results)
    assert out == {"rate": 0.0, "passed": 0, "total": 5}


# ---------------------------------------------------------------------------
# 3. patch_quality
# ---------------------------------------------------------------------------


# 功能：全应用 → 1.0
# 设计：3 patch 全 applied=1 / proposed=1 → 1.0
def test_patch_quality_all_applied() -> None:
    results = [
        _result("c1", patches=[_pr(1, 1, 1), _pr(2, 1, 1), _pr(3, 1, 1)]),
    ]
    out = patch_quality(results)
    assert out == {"rate": 1.0, "applied": 3, "proposed": 3}


# 功能：全失败 → 0.0
# 设计：2 patch applied=0 / proposed=2 → 0.0
def test_patch_quality_all_failed() -> None:
    results = [_result("c1", patches=[_pr(1, 2, 0), _pr(2, 1, 0)])]
    out = patch_quality(results)
    assert out == {"rate": 0.0, "applied": 0, "proposed": 3}


# 功能：混合 → 实际 applied / proposed
# 设计：1 patch 全应用 + 1 patch 部分应用 → 2/3
def test_patch_quality_mixed() -> None:
    results = [
        _result("c1", patches=[_pr(1, 2, 2), _pr(2, 1, 0)]),
    ]
    out = patch_quality(results)
    assert out["rate"] == pytest.approx(2 / 3)
    assert out["applied"] == 2
    assert out["proposed"] == 3


# ---------------------------------------------------------------------------
# 4. iteration_count
# ---------------------------------------------------------------------------


# 功能：单 case 的 iter_count 直接出
# 设计：1 case iter=3 → avg=3
def test_iteration_count_single_case() -> None:
    results = [_result("c1", iteration_count_=3)]
    out = iteration_count(results)
    assert out == {"avg": 3.0, "max": 3, "min": 3, "total": 3}


# 功能：多 case 的 avg/max/min/total
# 设计：3 case iter = 1, 2, 3 → avg=2 / max=3 / min=1 / total=6
def test_iteration_count_multiple_cases() -> None:
    results = [
        _result("c1", iteration_count_=1),
        _result("c2", iteration_count_=2),
        _result("c3", iteration_count_=3),
    ]
    out = iteration_count(results)
    assert out == {"avg": 2.0, "max": 3, "min": 1, "total": 6}


# 功能：空 results → 0
# 设计：传 [] → 0.0 / 0 / 0 / 0
def test_iteration_count_empty() -> None:
    out = iteration_count([])
    assert out == {"avg": 0.0, "max": 0, "min": 0, "total": 0}


# ---------------------------------------------------------------------------
# 5. time_to_first_pass
# ---------------------------------------------------------------------------


# 功能：全过 + 首个 iter 就过 → avg=1
# 设计：3 case 全 iter1 5/5 → avg=1
def test_time_to_first_pass_all_first_iter() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 5, 5)]),
        _result("c2", test_runs=[_tr(1, 3, 3)]),
        _result("c3", test_runs=[_tr(1, 1, 1)]),
    ]
    out = time_to_first_pass(results)
    assert out["avg"] == 1.0
    assert out["never_passed"] == 0


# 功能：iter 2 通过 → first_pass=2
# 设计：1 case iter1 0/3 + iter2 3/3 → first_pass=2
def test_time_to_first_pass_second_iter() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 3), _tr(2, 3, 3)]),
    ]
    out = time_to_first_pass(results)
    assert out["avg"] == 2.0
    assert out["p50"] == 2
    assert out["max"] == 2


# 功能：全败 → never_passed = total
# 设计：3 case 全 fail → never_passed=3
def test_time_to_first_pass_never_passed() -> None:
    results = [
        _result(f"c{i}", test_runs=[_tr(1, 0, 3), _tr(2, 0, 3)])
        for i in range(3)
    ]
    out = time_to_first_pass(results)
    assert out["avg"] == 0.0
    assert out["never_passed"] == 3


# ---------------------------------------------------------------------------
# 6. self_recovery_rate
# ---------------------------------------------------------------------------


# 功能：自愈 1 次 / 1 失败 → 1.0
# 设计：1 case iter1 fail / iter2 pass / recovery_count=1 → 1/1
def test_self_recovery_rate_all_recovered() -> None:
    results = [
        _result("c1", recovery_count=1, test_runs=[_tr(1, 0, 3), _tr(2, 3, 3)]),
    ]
    out = self_recovery_rate(results)
    assert out == {"rate": 1.0, "recoveries": 1, "failures": 1}


# 功能：自愈 0 / 失败 3 → 0.0
# 设计：1 case 全 3 轮失败 → 0/3
def test_self_recovery_rate_none_recovered() -> None:
    results = [
        _result("c1", recovery_count=0, test_runs=[_tr(1, 0, 3), _tr(2, 0, 3), _tr(3, 0, 3)]),
    ]
    out = self_recovery_rate(results)
    assert out == {"rate": 0.0, "recoveries": 0, "failures": 3}


# 功能：混合 → 1/3（case1 1 自愈 + 1 失败；case2 0 自愈 + 2 失败）
# 设计：失败次数 = 1 + 2 = 3；recoveries = 1
def test_self_recovery_rate_mixed() -> None:
    results = [
        _result("c1", recovery_count=1, test_runs=[_tr(1, 0, 3), _tr(2, 3, 3)]),
        _result("c2", recovery_count=0, test_runs=[_tr(1, 0, 3), _tr(2, 0, 3)]),
    ]
    out = self_recovery_rate(results)
    assert out["rate"] == pytest.approx(1 / 3)
    assert out["recoveries"] == 1
    assert out["failures"] == 3


# ---------------------------------------------------------------------------
# 7. compile_success_rate
# ---------------------------------------------------------------------------


# 功能：pytest collect 成功（total > 0）的轮次占比
# 设计：3 轮：2 成功 + 1 失败（total=0）→ 2/3
def test_compile_success_rate_mixed() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 3), _tr(2, 0, 0), _tr(3, 3, 3)]),
    ]
    out = compile_success_rate(results)
    assert out == {"rate": 2 / 3, "success_runs": 2, "total_runs": 3}


# 功能：全 collect 失败 → 0.0
# 设计：3 轮全 total=0 → 0/3
def test_compile_success_rate_all_collect_fail() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 0), _tr(2, 0, 0)]),
    ]
    out = compile_success_rate(results)
    assert out == {"rate": 0.0, "success_runs": 0, "total_runs": 2}


# 功能：全 collect 成功 → 1.0
# 设计：3 轮全 total > 0 → 3/3
def test_compile_success_rate_all_collect_pass() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 3), _tr(2, 3, 3), _tr(3, 3, 3)]),
    ]
    out = compile_success_rate(results)
    assert out == {"rate": 1.0, "success_runs": 3, "total_runs": 3}


# ---------------------------------------------------------------------------
# 8. test_growth_rate
# ---------------------------------------------------------------------------


# 功能：测试数增长 → 累计新增 / 配对数
# 设计：iter1 total=1 → iter2 total=3 → 新增 2，1 次配对 → 2.0
def test_growth_rate_increase() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 1), _tr(2, 2, 3)]),
    ]
    out = growth_rate(results)
    assert out == {"rate": 2.0, "tests_added": 2, "iterations": 1}


# 功能：测试数持平 → 0.0
# 设计：iter1 total=3 → iter2 total=3 → 0 新增
def test_growth_rate_flat() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 3), _tr(2, 3, 3)]),
    ]
    out = growth_rate(results)
    assert out == {"rate": 0.0, "tests_added": 0, "iterations": 1}


# 功能：测试数减少 → 0（max(0, ...) 防负数）
# 设计：iter1 total=5 → iter2 total=2 → 0 新增
def test_growth_rate_decrease() -> None:
    results = [
        _result("c1", test_runs=[_tr(1, 0, 5), _tr(2, 0, 2)]),
    ]
    out = growth_rate(results)
    assert out == {"rate": 0.0, "tests_added": 0, "iterations": 1}


# ---------------------------------------------------------------------------
# compute_all_coding_metrics + MetricsReport
# ---------------------------------------------------------------------------


# 功能：compute_all_coding_metrics 一键汇总 8 指标到 MetricsReport
# 设计：1 case 全过 → MetricsReport 含 8 个 metric
def test_compute_all_coding_metrics_returns_full_report() -> None:
    results = [
        _result(
            "c1",
            final_passed=2,
            success=True,
            iteration_count_=1,
            recovery_count=0,
            test_runs=[_tr(1, 2, 2)],
            patches=[_pr(1, 1, 1)],
        ),
    ]
    report = compute_all_coding_metrics(results, dataset_name="demo")
    assert isinstance(report, MetricsReport)
    assert report.dataset_name == "demo"
    assert report.case_count == 1
    assert set(report.metrics.keys()) == set(CODING_METRIC_NAMES)
    assert report.metrics["task_completion_rate"]["rate"] == 1.0
    assert report.metrics["patch_quality"]["rate"] == 1.0
    assert report.generated_at != ""


# 功能：MetricsReport.to_dict / to_json + 路径遍历保护
# 设计：to_json 写到 tmp_path → 再读回 JSON 比对；
#       to_json(带 ".." 段) → ValueError
def test_metrics_report_to_json_writes_and_rejects_traversal(tmp_path: Path) -> None:
    report = compute_all_coding_metrics(
        [_result("c1", final_passed=1, test_runs=[_tr(1, 1, 1)])],
        dataset_name="t",
    )
    out = tmp_path / "metrics.json"
    report.to_json(out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["dataset_name"] == "t"
    assert "task_completion_rate" in data["metrics"]
    # 路径遍历保护
    bad = Path("foo/../malicious.json")
    assert ".." in bad.parts
    with pytest.raises(ValueError):
        report.to_json(bad)


# 功能：CODING_METRIC_NAMES 含全部 8 个指标且按 plan §二.2.3 顺序
# 设计：直接 assert 8 个名字 + 顺序
def test_coding_metric_names_match_plan_order() -> None:
    expected = (
        "task_completion_rate",
        "tests_passed_rate",
        "patch_quality",
        "iteration_count",
        "time_to_first_pass",
        "self_recovery_rate",
        "compile_success_rate",
        "test_growth_rate",
    )
    assert CODING_METRIC_NAMES == expected
