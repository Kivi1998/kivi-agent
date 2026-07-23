"""评测数据集（agent: package-eval-dataset-v51）。

JSONL 格式：每行一个 EvalCase。
- 字段冻结（v1 契约内）：id / goal / expected_route / expected_tools /
  expected_sources / expected_answer / difficulty / tags / notes
- 加载路径必须排除 ".."（防路径遍历）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# v1 §1 锁定的 6 个业务 Tool 名（与 docs/contracts/v1.md 对齐）
# 用 Literal 限制 expected_tools 元素类型，pydantic 自动校验非法 tool 名
ToolName = Literal[
    "web_search",
    "rag_query",
    "query_database",
    "echarts_render",
    "memory_save",
    "memory_recall",
]

# v1 §1 + 业务路由决策的 5 种 intent（含 general 兜底）
RouteIntent = Literal["rag", "web_search", "database", "general", "synthesizer"]


# 单个评测 case（agent: package-eval-dataset-v51）
class EvalCase(BaseModel):
    """单个评测 case。

    字段约定（与 WT-G1 plan §三 一致）：
    - goal：用户任务描述（必填）
    - expected_route：路由决策期望值；用于路由正确率指标
    - expected_tools：业务 Tool 期望名列表；用于 Tool 选择正确率指标
    - expected_sources：RAG 引用 ID 期望值；用于 RAG 引用准确率指标
    - expected_answer：标准答案（Ground Truth）；Judge 评分用
    - difficulty / tags / notes：分类与人工备注
    """

    id: str
    goal: str
    tags: list[str] = Field(default_factory=list)
    # 期望值（用于指标计算）
    expected_route: RouteIntent | None = None
    expected_tools: list[ToolName] = Field(default_factory=list)
    expected_sources: list[str] = Field(default_factory=list)
    expected_answer: str | None = None
    # 元数据
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    notes: str | None = None


# 评测数据集（agent: package-eval-dataset-v51）
class EvalDataset(BaseModel):
    """评测数据集（JSONL 一行一 case）。"""

    name: str
    version: str = "1"
    cases: list[EvalCase]

    # 从 JSONL 文件加载数据集
    @classmethod
    def load(cls, path: Path) -> EvalDataset:
        """从 JSONL 文件加载（每行一个 EvalCase）。

        路径遍历保护：路径段含 ".." 时直接拒绝。
        """
        # 路径遍历保护：拒绝任何含 ".." 的路径
        if ".." in path.parts:
            raise ValueError(f"invalid dataset path: {path}")
        cases: list[EvalCase] = []
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cases.append(EvalCase(**data))
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"line {line_no} invalid: {e}") from e
        return cls(name=path.stem, cases=cases)

    # 按 tag 过滤数据集（返回新实例）
    def filter(self, tag: str) -> EvalDataset:
        """按 tag 过滤；返回新 EvalDataset（name 标记 tag）。"""
        return EvalDataset(
            name=f"{self.name}_tag_{tag}",
            version=self.version,
            cases=[c for c in self.cases if tag in c.tags],
        )
