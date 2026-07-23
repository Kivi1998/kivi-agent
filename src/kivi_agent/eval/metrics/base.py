"""Metric 抽象基类（agent: package-eval-metrics-v51）。"""
# base.py（agent: package-eval-metrics-v51）

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

# WT-G1 提供 EvalDataset / EvalResult；本 worktree 未合入故 type: ignore
# 集成时 WT-G1 合并后可移除 type: ignore
if TYPE_CHECKING:
    from kivi_agent.eval.dataset import EvalDataset  # type: ignore[import-not-found]
    from kivi_agent.eval.result import EvalResult  # type: ignore[import-not-found]


class Metric(ABC):
    """指标基类（agent: package-eval-metrics-v51）。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    # 计算指标值并返回键值字典
    def compute(
        self, dataset: EvalDataset, results: list[EvalResult]
    ) -> dict[str, Any]:
        """计算指标值并返回 {key: value} 字典。"""
        ...
