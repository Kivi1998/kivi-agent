"""总 Token（agent: package-eval-metrics-v51）。"""
# token.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset
    from kivi_agent.eval.result import EvalResult

from kivi_agent.eval.metrics.base import Metric


class TokenMetric(Metric):
    """总 Token：Σ input + output + cache_read tokens（agent: package-eval-metrics-v51）。"""

    name = "total_tokens"
    description = "Σ input + output + cache_read tokens"

    # 汇总输入、输出与缓存读取 Token
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        # 三个维度独立累加，便于上层 dashboard 拆分展示
        total_in = sum(r.input_tokens for r in results)
        total_out = sum(r.output_tokens for r in results)
        total_cache = sum(r.cache_read_tokens for r in results)
        return {
            "input": total_in,
            "output": total_out,
            "cache_read": total_cache,
            "total": total_in + total_out + total_cache,
        }
