"""Judge 集成（agent: package-eval-dataset-v51）。

复用 Wave 1 E 包的 Judge 修复版（必填 expected_answer + reference_context）。
本模块提供**离线降级版**（关键词重叠度），用于本地无 LLM 场景跑通端到端通路。
WT-G3 集成期：切到 `kivi_agent.evaluation.Judge`（LLM-as-judge），
构造时注入 FakeLlmProvider 即可端到端。
"""

from __future__ import annotations

from kivi_agent.eval.dataset import EvalCase
from kivi_agent.eval.result import EvalResult


# 给单 case 打分（agent: package-eval-dataset-v51）
def judge_case(case: EvalCase, result: EvalResult) -> tuple[float, str]:
    """对单 case 打分（关键词重叠度 0-1）。

    公式：|expected_answer ∩ final_answer 词集合| / |expected_answer 词集合|
    - 分母为 0 时返回 0.0（避免除零）
    - 中文按字 split 后效果差；演示版用例以英文/混合为主
    - WT-G3 集成期：本函数被替换为 `Judge(llm_provider=...).evaluate(...)`

    返回 (score, reason)；score ∈ [0.0, 1.0]。
    """
    if not case.expected_answer or not result.final_answer:
        return 0.0, "missing expected_answer or final_answer"

    expected_words = set(case.expected_answer.lower().split())
    actual_words = set(result.final_answer.lower().split())
    if not expected_words:
        return 0.0, "empty expected_answer"

    overlap = expected_words & actual_words
    score = len(overlap) / len(expected_words)
    reason = f"keyword overlap: {len(overlap)}/{len(expected_words)}"
    return min(score, 1.0), reason
