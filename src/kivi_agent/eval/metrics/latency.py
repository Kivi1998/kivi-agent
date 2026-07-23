"""平均延迟（agent: package-eval-metrics-v51）。"""
# latency.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset
    from kivi_agent.eval.result import EvalResult

from kivi_agent.eval.metrics.base import Metric


class LatencyMetric(Metric):
    """平均延迟：run.finished.ts - run.started.ts 平均值（agent: package-eval-metrics-v51）。"""

    name = "avg_latency_seconds"
    description = "run.finished.ts - run.started.ts 平均值"

    # 计算有效运行时长的平均值与分位数
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        # 容错收集：started_at / finished_at 任一缺失或 ISO 解析失败都跳过
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
        # 无有效样本时短路返回零值
        if not latencies:
            return {"avg_s": 0.0, "p50_s": 0.0, "p95_s": 0.0, "count": 0}
        # 排序后用索引切分位数（小样本不插值，简单一致）
        latencies.sort()
        n = len(latencies)
        return {
            "avg_s": sum(latencies) / n,
            "p50_s": latencies[n // 2],
            "p95_s": latencies[int(n * 0.95)],
            "count": n,
        }
