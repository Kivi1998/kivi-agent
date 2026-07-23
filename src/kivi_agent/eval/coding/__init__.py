"""T12 最小 coding agent + 8 指标（agent: package-eval-coding-v52）。

# coding/__init__.py（agent: package-eval-coding-v52）
Wave 5.2 WT-H2：自建最小 coding agent（kivi 内），不接 aigroup。
- CodingCase / CodingEvalResult / PatchRecord / TestRunRecord：数据类
- diff_parser：unified diff hunk 解析（patch 质量指标用）
- CodingAgent：LLM 写 patch → apply → pytest → 失败再修 的循环
- 沙箱隔离：所有文件写 `tempfile.TemporaryDirectory()`，不污染主仓库
- LLM 注入式（DI）：单测用 `FakeLlmProvider`
"""
from kivi_agent.eval.coding.coding_agent import CodingAgent
from kivi_agent.eval.coding.diff_parser import Hunk, parse_unified_diff
from kivi_agent.eval.coding.models import (
    CodingCase,
    CodingEvalResult,
    PatchRecord,
    TestRunRecord,
)

__all__ = [
    "CodingAgent",
    "CodingCase",
    "CodingEvalResult",
    "Hunk",
    "PatchRecord",
    "TestRunRecord",
    "parse_unified_diff",
]
