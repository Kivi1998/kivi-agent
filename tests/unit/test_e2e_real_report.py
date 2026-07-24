"""tests.e2e_real.report 单元测试（agent: package-e2e-real-w82）。

# test_e2e_real_report.py（agent: package-e2e-real-w82）
覆盖 4 个核心点：
- E2ERunResult 字段 + to_dict / to_json
- E2EReport.add + summary 聚合（总数 / 成功 / 失败 / token / cost / latency）
- E2EReport.to_json 落盘（schema 校验）
- E2EReport.to_markdown 落盘（标题 / 表格 / summary 段）
- compute_cost_usd（已知 model / 未知 model / 0 token）
- make_run_result 工厂函数
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.e2e_real.report import (
    DEFAULT_PRICING,
    E2EReport,
    E2ERunResult,
    compute_cost_usd,
    make_run_result,
)

# --- E2ERunResult 字段 ------------------------------------------------------------


# 功能：E2ERunResult 必填字段保留与赋值
# 设计：构造最小字段 → 读取全部字段值
def test_run_result_required_fields_round_trip() -> None:
    """``E2ERunResult`` 构造参数全部能读出。"""
    r = E2ERunResult(
        provider="anthropic",
        model="claude-sonnet-4-6",
        case_id="t1",
        case_name="test",
        started_at="2026-07-23T00:00:00+00:00",
        ended_at="2026-07-23T00:00:01+00:00",
        duration_seconds=1.0,
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.001,
        success=True,
    )
    assert r.provider == "anthropic"
    assert r.model == "claude-sonnet-4-6"
    assert r.case_id == "t1"
    assert r.case_name == "test"
    assert r.duration_seconds == 1.0
    assert r.input_tokens == 100
    assert r.output_tokens == 50
    assert r.total_tokens == 150
    assert r.cost_usd == 0.001
    assert r.success is True
    assert r.error is None
    assert r.output_quality_score is None
    assert r.output_preview == ""


# 功能：E2ERunResult.to_dict 字段全量
def test_run_result_to_dict_includes_all_fields() -> None:
    """``to_dict`` 包含 dataclass 全部字段（含 error / preview）。"""
    r = E2ERunResult(
        provider="openai",
        model="gpt-4o",
        case_id="x",
        case_name="X",
        started_at="t0",
        ended_at="t1",
        duration_seconds=0.5,
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.0,
        success=False,
        error="boom",
        output_preview="hello",
        output_quality_score=3,
    )
    d = r.to_dict()
    assert d["provider"] == "openai"
    assert d["model"] == "gpt-4o"
    assert d["case_id"] == "x"
    assert d["error"] == "boom"
    assert d["output_preview"] == "hello"
    assert d["output_quality_score"] == 3
    assert d["success"] is False
    # 全部 15 个字段
    assert len(d) == 15


# 功能：E2ERunResult.to_json 可解析
def test_run_result_to_json_is_valid_json() -> None:
    """``to_json`` 输出能被 json.loads 解析（保证非 ASCII 字符也 OK）。"""
    r = E2ERunResult(
        provider="anthropic",
        model="claude-sonnet-4-6",
        case_id="中文-id",
        case_name="中文 case 名",
        started_at="t0",
        ended_at="t1",
        duration_seconds=0.0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        success=True,
    )
    raw = r.to_json()
    parsed = json.loads(raw)
    assert parsed["case_id"] == "中文-id"
    assert parsed["case_name"] == "中文 case 名"


# --- E2EReport.summary ------------------------------------------------------------


# 功能：E2EReport 空时 summary 全 0
def test_report_summary_empty() -> None:
    """空 report 的 summary 全部为 0 / False。"""
    s = E2EReport().summary()
    assert s["total_cases"] == 0
    assert s["success_count"] == 0
    assert s["failure_count"] == 0
    assert s["success_rate"] == 0.0
    assert s["total_tokens"] == 0
    assert s["total_cost_usd"] == 0.0
    assert s["avg_latency_seconds"] == 0.0


# 功能：E2EReport 混合成功/失败的 summary
# 设计：3 成功 + 1 失败 → success_rate=0.75，total tokens=所有 case 之和
def test_report_summary_mixed_results() -> None:
    """混合 success / failure 时的 summary 聚合。"""
    r = E2EReport()
    # 3 成功
    for i in range(3):
        r.add(
            make_run_result(
                provider="anthropic",
                model="claude-sonnet-4-6",
                case_id=f"ok-{i}",
                case_name="ok",
                duration_seconds=1.0,
                input_tokens=100,
                output_tokens=50,
                success=True,
            )
        )
    # 1 失败
    r.add(
        make_run_result(
            provider="anthropic",
            model="claude-sonnet-4-6",
            case_id="bad-1",
            case_name="bad",
            duration_seconds=2.0,
            input_tokens=50,
            output_tokens=10,
            success=False,
            error="boom",
        )
    )
    s = r.summary()
    assert s["total_cases"] == 4
    assert s["success_count"] == 3
    assert s["failure_count"] == 1
    assert s["success_rate"] == 0.75
    assert s["total_input_tokens"] == 350
    assert s["total_output_tokens"] == 160
    assert s["total_tokens"] == 510
    # avg_latency = (1+1+1+2) / 4 = 1.25
    assert s["avg_latency_seconds"] == 1.25


# 功能：E2EReport.add 保持插入顺序
def test_report_add_preserves_order() -> None:
    """``add`` 按调用顺序保留；summary 顺序一致。"""
    r = E2EReport()
    for i in range(5):
        r.add(
            make_run_result(
                provider="anthropic",
                model="claude-sonnet-4-6",
                case_id=f"c-{i}",
                case_name=f"case-{i}",
                duration_seconds=0.1 * i,
                input_tokens=10,
                output_tokens=5,
                success=True,
            )
        )
    assert [r2.case_id for r2 in r.results] == ["c-0", "c-1", "c-2", "c-3", "c-4"]


# --- E2EReport.to_json ------------------------------------------------------------


# 功能：E2EReport.to_json 写文件结构正确
# 设计：构造 2 case → 写 tmp 文件 → 读回 → 校验顶层 schema
def test_report_to_json_writes_valid_file(tmp_path: Path) -> None:
    """``to_json`` 写出的 JSON 含 ``generated_at`` / ``summary`` / ``results`` 顶层字段。"""
    r = E2EReport()
    r.add(
        make_run_result(
            provider="anthropic",
            model="claude-sonnet-4-6",
            case_id="a",
            case_name="A",
            duration_seconds=1.0,
            input_tokens=100,
            output_tokens=50,
            success=True,
        )
    )
    r.add(
        make_run_result(
            provider="openai",
            model="gpt-4o",
            case_id="b",
            case_name="B",
            duration_seconds=0.5,
            input_tokens=80,
            output_tokens=40,
            success=False,
            error="timeout",
        )
    )
    p = tmp_path / "report.json"
    r.to_json(p)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "generated_at" in data
    assert "summary" in data
    assert "results" in data
    assert len(data["results"]) == 2
    assert data["summary"]["total_cases"] == 2
    assert data["summary"]["success_count"] == 1
    # results[0] 字段
    first = data["results"][0]
    assert first["case_id"] == "a"
    assert first["provider"] == "anthropic"
    assert first["success"] is True


# 功能：E2EReport.to_json 自动创建父目录
def test_report_to_json_creates_parent_dir(tmp_path: Path) -> None:
    """``to_json`` 自动 mkdir -p 父目录。"""
    r = E2EReport()
    r.add(
        make_run_result(
            provider="anthropic",
            model="claude-sonnet-4-6",
            case_id="a",
            case_name="A",
            duration_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            success=True,
        )
    )
    p = tmp_path / "deep" / "nested" / "report.json"
    r.to_json(p)
    assert p.exists()


# --- E2EReport.to_markdown --------------------------------------------------------


# 功能：E2EReport.to_markdown 写文件结构正确
# 设计：构造 2 case → 写 tmp .md → 校验含 summary 段 + 表格 + 每 case section
def test_report_to_markdown_writes_valid_file(tmp_path: Path) -> None:
    """``to_markdown`` 写出的 .md 含 summary 段 + 表格 + 每 case section。"""
    r = E2EReport()
    r.add(
        make_run_result(
            provider="anthropic",
            model="claude-sonnet-4-6",
            case_id="a",
            case_name="Case A",
            duration_seconds=1.0,
            input_tokens=100,
            output_tokens=50,
            success=True,
        )
    )
    r.add(
        make_run_result(
            provider="openai",
            model="gpt-4o",
            case_id="b",
            case_name="Case B",
            duration_seconds=0.5,
            input_tokens=80,
            output_tokens=40,
            success=False,
            error="timeout",
        )
    )
    p = tmp_path / "report.md"
    r.to_markdown(p)
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    # 标题 + summary 段
    assert "# Real LLM E2E Report" in text
    assert "## Summary" in text
    assert "Total cases:" in text
    assert "## Results" in text
    # 表格 header
    assert "| # | case_id |" in text
    # 表格行（含 case_id）
    assert "a" in text and "b" in text
    # 失败标记
    assert "❌" in text
    assert "✅" in text
    # 每 case section
    assert "### 1. a — Case A" in text
    assert "### 2. b — Case B" in text


# 功能：to_markdown 中文 case_name 正确序列化
def test_report_to_markdown_handles_chinese(tmp_path: Path) -> None:
    """``to_markdown`` 写中文 case_name 不报错。"""
    r = E2EReport()
    r.add(
        make_run_result(
            provider="anthropic",
            model="claude-sonnet-4-6",
            case_id="中文",
            case_name="中文 case 名",
            duration_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            success=True,
            output_preview="中文预览",
        )
    )
    p = tmp_path / "report.md"
    r.to_markdown(p)
    text = p.read_text(encoding="utf-8")
    assert "中文 case 名" in text
    assert "中文预览" in text


# --- compute_cost_usd ------------------------------------------------------------


# 功能：compute_cost_usd 已知 model 按 PricingTable 计算
def test_compute_cost_usd_known_model() -> None:
    """``claude-sonnet-4-6`` 按 DEFAULT_PRICING 计算。"""
    in_price, out_price = DEFAULT_PRICING["claude-sonnet-4-6"]
    expected = (1000 / 1000.0) * in_price + (500 / 1000.0) * out_price
    assert compute_cost_usd("claude-sonnet-4-6", 1000, 500) == expected


# 功能：compute_cost_usd 未知 model 走 DEFAULT_FALLBACK_PRICE
def test_compute_cost_usd_unknown_model_uses_fallback() -> None:
    """未在 PricingTable 的 model 走 DEFAULT_FALLBACK_PRICE。"""
    from tests.e2e_real.report import DEFAULT_FALLBACK_PRICE

    in_price, out_price = DEFAULT_FALLBACK_PRICE
    expected = (1000 / 1000.0) * in_price + (500 / 1000.0) * out_price
    assert compute_cost_usd("unknown-model-xyz", 1000, 500) == expected


# 功能：compute_cost_usd 0 token → cost 0
def test_compute_cost_usd_zero_tokens() -> None:
    """0 token 时 cost = 0.0。"""
    assert compute_cost_usd("claude-sonnet-4-6", 0, 0) == 0.0


# --- make_run_result 工厂 --------------------------------------------------------


# 功能：make_run_result 自动算 cost + 时间戳
def test_make_run_result_computes_cost_and_total() -> None:
    """工厂函数自动算 ``cost_usd`` / ``total_tokens`` / ``ended_at``。"""
    import pytest

    r = make_run_result(
        provider="anthropic",
        model="claude-sonnet-4-6",
        case_id="c",
        case_name="C",
        duration_seconds=1.0,
        input_tokens=1000,
        output_tokens=500,
        success=True,
    )
    # 期望 cost = 1000/1000 * 0.003 + 500/1000 * 0.015 = 0.003 + 0.0075 = 0.0105
    assert r.cost_usd == pytest.approx(0.0105)
    assert r.total_tokens == 1500
    assert r.success is True
    # started_at 与 ended_at 一致（_now_iso 同次调用）
    assert r.started_at == r.ended_at
