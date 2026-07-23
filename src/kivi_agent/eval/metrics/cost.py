"""总成本（agent: package-eval-metrics-v51）。

价格表从 config.example.toml 加载：
[pricing]
"claude-sonnet-4-6" = [0.003, 0.015]  # (input_per_1k, output_per_1k)
"""
# cost.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset
    from kivi_agent.eval.result import EvalResult

from kivi_agent.eval.metrics.base import Metric


class CostMetric(Metric):
    """总成本：Σ (input * price_in + output * price_out)（agent: package-eval-metrics-v51）。"""

    name = "total_cost_usd"
    description = "Σ (input * price_in + output * price_out)"

    # 默认价格表（与 config.example.toml 同步）；上层可通过 __init__ 注入自定义表
    DEFAULT_PRICING: dict[str, tuple[float, float]] = {
        "claude-sonnet-4-6": (0.003, 0.015),
        "claude-haiku-4-5": (0.0008, 0.004),
        "gpt-4o": (0.005, 0.015),
    }

    # 初始化模型价格表
    def __init__(self, pricing: dict[str, tuple[float, float]] | None = None) -> None:
        # None 时退化到内建默认值；未注册的 model 走默认 sonnet 单价
        self._pricing = pricing if pricing is not None else self.DEFAULT_PRICING

    # 按默认模型单价计算总成本与平均成本
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        # Wave 5.1 简化策略：默认按 sonnet 单价（与 dataset 默认 model 对齐）
        # Wave 5.2 计划支持 per-case model 维度
        model = "claude-sonnet-4-6"
        in_price, out_price = self._pricing.get(model, (0.003, 0.015))
        total_cost = 0.0
        for r in results:
            # 单价是 per 1k token，先除 1000
            cost = (r.input_tokens / 1000.0) * in_price + (r.output_tokens / 1000.0) * out_price
            total_cost += cost
        return {
            "total_usd": round(total_cost, 4),
            "model": model,
            "per_case_avg_usd": round(total_cost / len(results), 4) if results else 0.0,
        }
