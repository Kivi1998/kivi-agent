"""7 指标 + 汇总报告 单元测试（agent: package-eval-metrics-v51）。

覆盖（plan §三 WT-G2）：
- TaskSuccessMetric / RouteAccuracyMetric / ToolAccuracyMetric /
  RagCitationMetric / LatencyMetric / TokenMetric / CostMetric
- MetricsReport.to_dict / to_json / 路径遍历保护
- compute_all_metrics 一键计算 7 指标
"""
# test_metrics.py（agent: package-eval-metrics-v51）

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from kivi_agent.eval.metrics import (
    CostMetric,
    LatencyMetric,
    RagCitationMetric,
    RouteAccuracyMetric,
    TaskSuccessMetric,
    TokenMetric,
    ToolAccuracyMetric,
    compute_all_metrics,
)

# ---------------------------------------------------------------------------
# 测试替身：WT-G1 尚未合入本 worktree，仅提供指标访问的最小字段
# ---------------------------------------------------------------------------


@dataclass
class EvalCase:
    """评测 case 测试替身。"""

    id: str
    goal: str = ""
    expected_route: str | None = None
    expected_tools: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)


@dataclass
class EvalDataset:
    """评测数据集测试替身。"""

    name: str
    cases: list[EvalCase] = field(default_factory=list)


@dataclass
class ToolCall:
    """Tool 调用测试替身。"""

    tool_name: str


@dataclass
class EvalResult:
    """评测结果测试替身。"""

    case_id: str
    success: bool = False
    route_decision: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    rag_sources: list[dict[str, Any]] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


# ---------------------------------------------------------------------------
# 工厂：构造测试数据
# ---------------------------------------------------------------------------


# 构造最小 EvalCase 测试数据
def _case(
    case_id: str = "c1",
    expected_route: str | None = None,
    expected_tools: list[str] | None = None,
    expected_sources: list[str] | None = None,
) -> EvalCase:
    """构造最小 EvalCase（agent: package-eval-metrics-v51）。"""
    return EvalCase(
        id=case_id,
        goal=f"goal for {case_id}",
        expected_route=expected_route,
        expected_tools=expected_tools or [],
        expected_sources=expected_sources or [],
    )


# 构造最小 EvalResult 测试数据
def _result(
    case_id: str = "c1",
    success: bool = False,
    intent: str | None = None,
    tool_names: list[str] | None = None,
    source_ids: list[str] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> EvalResult:
    """构造最小 EvalResult（agent: package-eval-metrics-v51）。"""
    return EvalResult(
        case_id=case_id,
        success=success,
        route_decision={"intent": intent} if intent is not None else None,
        tool_calls=[ToolCall(tool_name=n) for n in (tool_names or [])],
        rag_sources=[{"id": i} for i in (source_ids or [])],
        started_at=started_at,
        finished_at=finished_at,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
    )


# ---------------------------------------------------------------------------
# TaskSuccessMetric
# ---------------------------------------------------------------------------


# 功能：全成功场景下 rate=1.0 / passed=总数
# 设计：构造 3 个 success=True 的结果，断言 rate 与 passed / total 一致
def test_task_success_all_pass() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2"), _case("c3")])
    results = [_result("c1", success=True), _result("c2", success=True), _result("c3", success=True)]
    out = TaskSuccessMetric().compute(ds, results)
    assert out == {"rate": 1.0, "passed": 3, "total": 3}


# 功能：全失败场景下 rate=0.0
# 设计：3 个 success=False 的结果，断言 rate=0.0 且 passed=0
def test_task_success_all_fail() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2")])
    results = [_result("c1", success=False), _result("c2", success=False)]
    out = TaskSuccessMetric().compute(ds, results)
    assert out == {"rate": 0.0, "passed": 0, "total": 2}


# 功能：空 results 短路返回，避免除零
# 设计：直接传入空列表，断言 0.0 / 0 / 0（不抛异常）
def test_task_success_empty_results() -> None:
    ds = EvalDataset(name="t", cases=[])
    out = TaskSuccessMetric().compute(ds, [])
    assert out == {"rate": 0.0, "passed": 0, "total": 0}


# ---------------------------------------------------------------------------
# RouteAccuracyMetric
# ---------------------------------------------------------------------------


# 功能：所有 case 都路由正确时 rate=1.0
# 设计：3 个 case 都有 expected_route 且 route_decision.intent 全部匹配
def test_route_accuracy_all_match() -> None:
    ds = EvalDataset(
        name="t",
        cases=[_case("c1", expected_route="web_search"), _case("c2", expected_route="rag_query")],
    )
    results = [_result("c1", intent="web_search"), _result("c2", intent="rag_query")]
    out = RouteAccuracyMetric().compute(ds, results)
    assert out == {"rate": 1.0, "matched": 2, "applicable": 2}


# 功能：半匹配 + 半数无 expected_route 时 rate 只在 applicable 子集上计算
# 设计：3 个 case 仅有 2 个有 expected_route，其中 1 个匹配
def test_route_accuracy_partial_match() -> None:
    ds = EvalDataset(
        name="t",
        cases=[
            _case("c1", expected_route="web_search"),
            _case("c2", expected_route="rag_query"),
            _case("c3", expected_route=None),  # 不适用
        ],
    )
    results = [
        _result("c1", intent="web_search"),  # match
        _result("c2", intent="query_database"),  # miss
        _result("c3", intent="web_search"),  # 不计入
    ]
    out = RouteAccuracyMetric().compute(ds, results)
    assert out == {"rate": 0.5, "matched": 1, "applicable": 2}


# 功能：所有 case 都缺 expected_route 或 route_decision 时 rate=0.0
# 设计：applicable=0 时短路返回 0.0 而非抛 ZeroDivisionError
def test_route_accuracy_no_applicable() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2")])
    results = [_result("c1"), _result("c2")]  # 都无 intent
    out = RouteAccuracyMetric().compute(ds, results)
    assert out == {"rate": 0.0, "matched": 0, "applicable": 0}


# ---------------------------------------------------------------------------
# ToolAccuracyMetric
# ---------------------------------------------------------------------------


# 功能：实际 tool_calls 与 expected_tools 完全一致时 exact=contain=1.0
# 设计：3 个 case 集合完全相同，断言两种 rate 都为 1.0
def test_tool_accuracy_exact_match() -> None:
    ds = EvalDataset(
        name="t",
        cases=[
            _case("c1", expected_tools=["web_search"]),
            _case("c2", expected_tools=["rag_query", "echarts_render"]),
        ],
    )
    results = [
        _result("c1", tool_names=["web_search"]),
        _result("c2", tool_names=["rag_query", "echarts_render"]),
    ]
    out = ToolAccuracyMetric().compute(ds, results)
    assert out == {"exact_match_rate": 1.0, "contain_match_rate": 1.0, "applicable": 2}


# 功能：实际集合是期望的超集时 contain_match 计入而 exact_match 不计入
# 设计：调了 2 个 tool 期望 1 个；assert exact=0.5 / contain=1.0
def test_tool_accuracy_contain_match_only() -> None:
    ds = EvalDataset(
        name="t",
        cases=[
            _case("c1", expected_tools=["web_search"]),
            _case("c2", expected_tools=["rag_query"]),
        ],
    )
    results = [
        _result("c1", tool_names=["web_search", "memory_save"]),  # 超集
        _result("c2", tool_names=["rag_query"]),  # 精确
    ]
    out = ToolAccuracyMetric().compute(ds, results)
    assert out == {"exact_match_rate": 0.5, "contain_match_rate": 1.0, "applicable": 2}


# 功能：完全没调期望的 tool 时两种 rate 都不计
# 设计：调了其它 tool 但没调 expected；assert exact=contain=0.0
def test_tool_accuracy_no_match() -> None:
    ds = EvalDataset(
        name="t",
        cases=[_case("c1", expected_tools=["web_search"]), _case("c2", expected_tools=["rag_query"])],
    )
    results = [
        _result("c1", tool_names=["memory_save"]),  # 漏调
        _result("c2", tool_names=["echarts_render"]),  # 漏调
    ]
    out = ToolAccuracyMetric().compute(ds, results)
    assert out == {"exact_match_rate": 0.0, "contain_match_rate": 0.0, "applicable": 2}


# ---------------------------------------------------------------------------
# RagCitationMetric
# ---------------------------------------------------------------------------


# 功能：所有期望引用都在实际引用中时 rate=1.0
# 设计：实际集合是期望的超集也不扣分（与 plan §二 公式对齐：多引用不计负）
def test_rag_citation_all_cited() -> None:
    ds = EvalDataset(
        name="t",
        cases=[
            _case("c1", expected_sources=["doc1", "doc2"]),
            _case("c2", expected_sources=["doc3"]),
        ],
    )
    results = [
        _result("c1", source_ids=["doc1", "doc2", "extra"]),
        _result("c2", source_ids=["doc3"]),
    ]
    out = RagCitationMetric().compute(ds, results)
    assert out == {"rate": 1.0, "matched": 2, "applicable": 2}


# 功能：部分 case 缺引用时按比例计 rate
# 设计：2 个 case 期望引用，1 个实际全缺；rate=0.5
def test_rag_citation_partial_cited() -> None:
    ds = EvalDataset(
        name="t",
        cases=[
            _case("c1", expected_sources=["doc1"]),
            _case("c2", expected_sources=["doc2", "doc3"]),
        ],
    )
    results = [
        _result("c1", source_ids=["doc1"]),  # 命中
        _result("c2", source_ids=["doc2"]),  # 漏 doc3
    ]
    out = RagCitationMetric().compute(ds, results)
    assert out == {"rate": 0.5, "matched": 1, "applicable": 2}


# 功能：完全没引到期望时 rate=0.0
# 设计：实际源与期望无交集；assert matched=0
def test_rag_citation_no_citation() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1", expected_sources=["doc1"])])
    results = [_result("c1", source_ids=["other_doc"])]
    out = RagCitationMetric().compute(ds, results)
    assert out == {"rate": 0.0, "matched": 0, "applicable": 1}


# ---------------------------------------------------------------------------
# LatencyMetric
# ---------------------------------------------------------------------------


# 功能：单个 case 时 avg/p50/p95 都等于该 case 延迟
# 设计：1.5s 延迟；n=1 时 p50=latencies[0]，p95=int(1*0.95)=0
def test_latency_single_case() -> None:
    t0 = "2026-07-23T10:00:00+00:00"
    t1 = "2026-07-23T10:00:01.500000+00:00"
    ds = EvalDataset(name="t", cases=[_case("c1")])
    results = [_result("c1", started_at=t0, finished_at=t1)]
    out = LatencyMetric().compute(ds, results)
    assert out["avg_s"] == pytest.approx(1.5)
    assert out["count"] == 1


# 功能：多个 case 时返回 avg / p50 / p95 三档
# 设计：构造 4 个 case 延迟 1/2/3/4s；验证三档数值
def test_latency_multi_case_percentiles() -> None:
    base = datetime.fromisoformat("2026-07-23T10:00:00+00:00")
    ds = EvalDataset(name="t", cases=[_case(f"c{i}") for i in range(4)])
    results = []
    for i, secs in enumerate([1.0, 2.0, 3.0, 4.0]):
        t0 = base.isoformat()
        t1 = (base + timedelta(seconds=secs)).isoformat()
        results.append(_result(f"c{i}", started_at=t0, finished_at=t1))
    out = LatencyMetric().compute(ds, results)
    assert out["avg_s"] == pytest.approx(2.5)
    assert out["count"] == 4
    # 4 个样本：p50=latencies[2]=3.0，p95=latencies[int(4*0.95)]=latencies[3]=4.0
    assert out["p50_s"] == pytest.approx(3.0)
    assert out["p95_s"] == pytest.approx(4.0)


# 功能：缺 started_at / finished_at 或 ISO 非法时跳过该 case
# 设计：3 个 result 中 1 个无时间戳，1 个时间格式错；仅 1 个计入 count
def test_latency_skip_invalid() -> None:
    base = datetime.fromisoformat("2026-07-23T10:00:00+00:00")
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2"), _case("c3")])
    results = [
        _result("c1", started_at=base.isoformat(), finished_at=(base + timedelta(seconds=2)).isoformat()),
        _result("c2", started_at=None, finished_at=None),  # 跳过
        _result("c3", started_at="not-iso", finished_at="also-not-iso"),  # 跳过（ValueError）
    ]
    out = LatencyMetric().compute(ds, results)
    assert out["count"] == 1
    assert out["avg_s"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# TokenMetric
# ---------------------------------------------------------------------------


# 功能：多 case 的 input/output/cache 各自累加
# 设计：3 个 case 三档 token 独立求和；total = sum
def test_token_accumulate() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2"), _case("c3")])
    results = [
        _result("c1", input_tokens=100, output_tokens=50, cache_read_tokens=20),
        _result("c2", input_tokens=200, output_tokens=80, cache_read_tokens=30),
        _result("c3", input_tokens=300, output_tokens=120, cache_read_tokens=50),
    ]
    out = TokenMetric().compute(ds, results)
    assert out == {"input": 600, "output": 250, "cache_read": 100, "total": 950}


# 功能：全零 token 时三档都为 0，total=0
# 设计：所有 token 字段都是 0
def test_token_zero() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2")])
    results = [_result("c1"), _result("c2")]
    out = TokenMetric().compute(ds, results)
    assert out == {"input": 0, "output": 0, "cache_read": 0, "total": 0}


# ---------------------------------------------------------------------------
# CostMetric
# ---------------------------------------------------------------------------


# 功能：使用默认 sonnet 单价（0.003/0.015 per 1k）计算总成本
# 设计：1000 input + 2000 output；cost = 1*0.003 + 2*0.015 = 0.033
def test_cost_default_pricing() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1")])
    results = [_result("c1", input_tokens=1000, output_tokens=2000)]
    out = CostMetric().compute(ds, results)
    assert out["total_usd"] == pytest.approx(0.033)
    assert out["model"] == "claude-sonnet-4-6"


# 功能：自定义价格表生效（per 1k 单价替换）
# 设计：注入 {"claude-sonnet-4-6": (0.01, 0.03)}；1000 in + 1000 out = 0.04
def test_cost_custom_pricing() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1")])
    results = [_result("c1", input_tokens=1000, output_tokens=1000)]
    out = CostMetric(pricing={"claude-sonnet-4-6": (0.01, 0.03)}).compute(ds, results)
    assert out["total_usd"] == pytest.approx(0.04)


# 功能：浮点精度 round 到 4 位小数（避免 dashboard 显示长尾）
# 设计：构造会产生长浮点尾数的 input/output（1/3 token）；断言返回值已 round
def test_cost_float_rounding() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1")])
    # 333 input + 666 output：cost = 0.333*0.003 + 0.666*0.015 ≈ 0.010989
    results = [_result("c1", input_tokens=333, output_tokens=666)]
    out = CostMetric().compute(ds, results)
    # 4 位小数；与原值乘 10000 后取整一致
    assert out["total_usd"] == round(out["total_usd"], 4)
    assert out["per_case_avg_usd"] == round(out["per_case_avg_usd"], 4)


# 功能：多 case 时 per_case_avg = total / case_count
# 设计：2 个 case 相同 token；per_case_avg == total/2
def test_cost_per_case_average() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1"), _case("c2")])
    results = [
        _result("c1", input_tokens=1000, output_tokens=1000),
        _result("c2", input_tokens=1000, output_tokens=1000),
    ]
    out = CostMetric().compute(ds, results)
    assert out["per_case_avg_usd"] == pytest.approx(out["total_usd"] / 2)


# ---------------------------------------------------------------------------
# MetricsReport + compute_all_metrics
# ---------------------------------------------------------------------------


# 功能：compute_all_metrics 一次性输出 7 指标 + dataset 元信息
# 设计：构造 1 个全成功 case，断言 metrics dict 含 7 个 name 键且 dataset_name/case_count 正确
def test_compute_all_metrics_returns_seven() -> None:
    t0 = "2026-07-23T10:00:00+00:00"
    t1 = "2026-07-23T10:00:01+00:00"
    ds = EvalDataset(
        name="demo",
        cases=[
            _case("c1", expected_route="web_search", expected_tools=["web_search"], expected_sources=["d1"]),
        ],
    )
    results = [
        _result(
            "c1",
            success=True,
            intent="web_search",
            tool_names=["web_search"],
            source_ids=["d1"],
            started_at=t0,
            finished_at=t1,
            input_tokens=100,
            output_tokens=50,
        )
    ]
    report = compute_all_metrics(ds, results)
    assert report.dataset_name == "demo"
    assert report.case_count == 1
    assert set(report.metrics.keys()) == {
        "task_success_rate",
        "route_accuracy",
        "tool_selection_accuracy",
        "rag_citation_accuracy",
        "avg_latency_seconds",
        "total_tokens",
        "total_cost_usd",
    }


# 功能：MetricsReport.to_dict 输出 dataclass 全字段
# 设计：构造 report 后调 to_dict；断言与原对象字段一一对应
def test_metrics_report_to_dict() -> None:
    ds = EvalDataset(name="t", cases=[_case("c1")])
    report = compute_all_metrics(ds, [_result("c1", success=True)])
    d = report.to_dict()
    assert d["dataset_name"] == "t"
    assert d["case_count"] == 1
    assert "metrics" in d and "task_success_rate" in d["metrics"]
    assert "generated_at" in d and d["generated_at"]  # ISO 字符串非空


# 功能：MetricsReport.to_json 写入合法 UTF-8 JSON 文件
# 设计：写入 tmp_path，读回 json 验证内容
def test_metrics_report_to_json_roundtrip(tmp_path: Path) -> None:
    ds = EvalDataset(name="t", cases=[_case("c1")])
    report = compute_all_metrics(ds, [_result("c1", success=True)])
    out_path = tmp_path / "report.json"
    report.to_json(out_path)
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["dataset_name"] == "t"
    assert data["metrics"]["task_success_rate"]["rate"] == 1.0


# 功能：路径含 `..` 时 to_json 直接拒绝
# 设计：传入包含 `..` 段的 Path；断言抛 ValueError（与 plan §六 风险缓解一致）
def test_metrics_report_to_json_rejects_traversal(tmp_path: Path) -> None:
    ds = EvalDataset(name="t", cases=[])
    report = compute_all_metrics(ds, [])
    # 在 Linux/macOS 上 `..` 一定是路径段之一
    bad = Path("safe") / ".." / "evil.json"
    with pytest.raises(ValueError, match="invalid path"):
        report.to_json(bad)
