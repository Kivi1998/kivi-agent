"""Eval 路由 5 case 真实 LLM 端到端（agent: package-e2e-real-w82）。

# test_eval_routing_e2e.py（agent: package-e2e-real-w82）
Wave 8.2 WT-L3：跑 ``kivi-eval`` on ``docs/eval-demos/basic-routing-10cases.jsonl``
前 5 case，记录每 case E2ERunResult。

env guard：``KIVI_RUN_E2E != "1"`` 时整个 module skip。
case 数限制：``KIVI_E2E_MAX_CASES``（默认 5）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from kivi_agent.eval.dataset import EvalDataset
from kivi_agent.eval.runner import EvalRunner
from tests.e2e_real.report import make_run_result

pytestmark = pytest.mark.skipif(
    os.environ.get("KIVI_RUN_E2E") != "1",
    reason="KIVI_RUN_E2E != 1; set KIVI_RUN_E2E=1 to run real LLM e2e",
)


# 数据集路径：相对 worktree 根（agent: package-e2e-real-w82）
DATASET_PATH = Path(__file__).resolve().parents[2] / "docs" / "eval-demos" / "basic-routing-10cases.jsonl"


# 跑前 5 case 真实 LLM 路由（agent: package-e2e-real-w82）
async def test_eval_routing_first_5_cases(e2e_report, max_cases: int) -> None:
    """跑 ``basic-routing-10cases.jsonl`` 前 ``KIVI_E2E_MAX_CASES``（默认 5）个 case。"""
    from tests.e2e_real.conftest import resolve_provider_name  # noqa: PLC0415

    if not DATASET_PATH.exists():
        pytest.skip(f"dataset not found: {DATASET_PATH}")

    dataset = EvalDataset.load(DATASET_PATH)
    cases_to_run = dataset.cases[:max_cases]

    runner = EvalRunner(concurrency=1)
    results = await runner.run_dataset(EvalDataset(name=dataset.name, cases=cases_to_run))

    for case, result in zip(cases_to_run, results, strict=True):
        # 评估结果摘要
        intent = (result.route_decision or {}).get("intent", "general")
        success = result.success
        error_msg = result.error
        run_result = make_run_result(
            provider=resolve_provider_name(),
            model=os.environ.get("KIVI_LLM_DEFAULT_MODEL", "claude-sonnet-4-6"),
            case_id=case.id,
            case_name=f"eval-routing/{intent} — {case.goal[:40]}",
            duration_seconds=0.0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            success=success,
            output_preview=result.final_answer or "",
            error=error_msg,
        )
        e2e_report.add(run_result)
        # 校验：路由 intent 等于期望（与 Wave 8.2 plan §三 WT-L3 对齐）
        if case.expected_route and intent != case.expected_route:
            # 不 hard fail；记录到 error 字段
            run_result.success = False
            run_result.error = (
                f"route mismatch: expected={case.expected_route} got={intent}"
            )
