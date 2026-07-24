"""真实 LLM E2E 测试报告模型（agent: package-e2e-real-w82）。

# report.py（agent: package-e2e-real-w82）
WT-L3 E2E 报告数据结构：
- E2ERunResult：单 case 一次真实 LLM 调用的完整记录
  （provider / model / tokens / cost / latency / success / output_preview / 人工评分）
- E2EReport：聚合多个 result；支持 JSON 落盘 + Markdown 表格导出 + summary 聚合

设计要点：
- 全 dataclass，JSON 序列化用 asdict（避免 pydantic 依赖循环）
- 字段顺序与 Wave 8.2 plan §三 WT-L3 "报告字段" 对齐
- 成本计算：可注入 PricingTable；缺省用 EvalRunner.DEFAULT_TOKEN_PRICING 的模型价
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 缺省 token 单价（每 1k token 的 USD 价格；与 EvalRunner.DEFAULT_TOKEN_PRICING 对齐）
# input_price_per_1k, output_price_per_1k
DEFAULT_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5": (0.0008, 0.004),
    "gpt-4o": (0.005, 0.015),
}


# 缺省单价：模型未在表中时使用（agent: package-e2e-real-w82）
DEFAULT_FALLBACK_PRICE: tuple[float, float] = (0.003, 0.015)


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class E2ERunResult:
    """单次真实 LLM E2E 调用结果（agent: package-e2e-real-w82）。"""

    provider: str
    model: str
    case_id: str
    case_name: str
    started_at: str
    ended_at: str
    duration_seconds: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    success: bool
    error: str | None = None
    # 人工评分（0-5；默认 None 表示尚未打分，由用户在报告中手动填）
    output_quality_score: int | None = None
    output_preview: str = ""

    # 序列化为 dict（agent: package-e2e-real-w82）
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # 序列化为 JSON 字符串（agent: package-e2e-real-w82）
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class E2EReport:
    """多次 E2E 调用的聚合报告（agent: package-e2e-real-w82）。"""

    results: list[E2ERunResult] = field(default_factory=list)

    # 追加一条结果（agent: package-e2e-real-w82）
    def add(self, result: E2ERunResult) -> None:
        """追加单次 E2E 调用结果；保持插入顺序。"""
        self.results.append(result)

    # JSON 落盘（agent: package-e2e-real-w82）
    def to_json(self, path: Path) -> None:
        """把整份报告写入 JSON 文件；含 summary 顶层字段。"""
        payload: dict[str, Any] = {
            "generated_at": _now_iso(),
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Markdown 表格落盘（agent: package-e2e-real-w82）
    def to_markdown(self, path: Path) -> None:
        """把整份报告写入 Markdown 文件；表格 + summary 段。"""
        lines: list[str] = []
        lines.append("# Real LLM E2E Report")
        lines.append("")
        lines.append(f"Generated: {_now_iso()}")
        lines.append("")

        # Summary
        s = self.summary()
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total cases: **{s['total_cases']}**")
        lines.append(f"- Success: **{s['success_count']}** ({s['success_rate'] * 100:.1f}%)")
        lines.append(f"- Failure: **{s['failure_count']}**")
        lines.append(f"- Total tokens: **{s['total_tokens']}**")
        lines.append(f"- Total cost (USD): **${s['total_cost_usd']:.4f}**")
        lines.append(f"- Avg latency: **{s['avg_latency_seconds']:.2f}s**")
        lines.append("")

        # Table header
        lines.append("## Results")
        lines.append("")
        lines.append(
            "| # | case_id | case_name | provider | model | in_tok | out_tok | "
            "cost_usd | latency_s | success | quality |"
        )
        lines.append(
            "|---|---------|-----------|----------|-------|--------|--------|"
            "----------|-----------|---------|---------|"
        )
        for i, r in enumerate(self.results, 1):
            quality = "-" if r.output_quality_score is None else str(r.output_quality_score)
            err = "" if r.success else f" ⚠️ {r.error or 'error'}"
            lines.append(
                f"| {i} | {r.case_id} | {r.case_name} | {r.provider} | {r.model} | "
                f"{r.input_tokens} | {r.output_tokens} | ${r.cost_usd:.4f} | "
                f"{r.duration_seconds:.2f} | {'✅' if r.success else '❌'}{err} | {quality} |"
            )
        lines.append("")
        # Output previews
        for i, r in enumerate(self.results, 1):
            lines.append(f"### {i}. {r.case_id} — {r.case_name}")
            lines.append("")
            if r.output_preview:
                lines.append(f"> {r.output_preview[:300]}")
            else:
                lines.append("_(no output preview)_")
            lines.append("")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    # 汇总统计（agent: package-e2e-real-w82）
    def summary(self) -> dict[str, Any]:
        """聚合统计：总数 / 成功率 / 总 token / 总 cost / 平均延迟。"""
        total = len(self.results)
        if total == 0:
            return {
                "total_cases": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "total_tokens": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_latency_seconds": 0.0,
            }
        success = sum(1 for r in self.results if r.success)
        total_in = sum(r.input_tokens for r in self.results)
        total_out = sum(r.output_tokens for r in self.results)
        total_cost = sum(r.cost_usd for r in self.results)
        avg_lat = sum(r.duration_seconds for r in self.results) / total
        return {
            "total_cases": total,
            "success_count": success,
            "failure_count": total - success,
            "success_rate": success / total,
            "total_tokens": total_in + total_out,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_cost_usd": total_cost,
            "avg_latency_seconds": avg_lat,
        }


# 按 model 计算单 case 的成本（agent: package-e2e-real-w82）
def compute_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, tuple[float, float]] | None = None,
) -> float:
    """根据 token 单价表计算单次调用的 USD 成本（输入/输出分别计费）。"""
    table = pricing if pricing is not None else DEFAULT_PRICING
    in_price, out_price = table.get(model, DEFAULT_FALLBACK_PRICE)
    return (input_tokens / 1000.0) * in_price + (output_tokens / 1000.0) * out_price


# 工厂：构造一个 E2ERunResult（agent: package-e2e-real-w82）
def make_run_result(
    *,
    provider: str,
    model: str,
    case_id: str,
    case_name: str,
    duration_seconds: float,
    input_tokens: int,
    output_tokens: int,
    success: bool,
    output_preview: str = "",
    error: str | None = None,
    pricing: dict[str, tuple[float, float]] | None = None,
    now_fn: Callable[[], str] = _now_iso,
) -> E2ERunResult:
    """便捷构造 E2ERunResult；自动算 cost_usd / total_tokens / 时间戳。"""
    cost = compute_cost_usd(model, input_tokens, output_tokens, pricing=pricing)
    ended = now_fn()
    return E2ERunResult(
        provider=provider,
        model=model,
        case_id=case_id,
        case_name=case_name,
        started_at=ended,  # 简化：单 case 时间精度内 started == ended
        ended_at=ended,
        duration_seconds=duration_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=cost,
        success=success,
        error=error,
        output_preview=output_preview,
    )


__all__ = [
    "DEFAULT_PRICING",
    "DEFAULT_FALLBACK_PRICE",
    "E2EReport",
    "E2ERunResult",
    "compute_cost_usd",
    "make_run_result",
]
