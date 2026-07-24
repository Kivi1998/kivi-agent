"""Demo 5 综合多能力 Agent 真实 LLM 端到端（agent: package-e2e-real-w82）。

# test_demo5_multi_agent_e2e.py（agent: package-e2e-real-w82）
Wave 8.2 WT-L3：跑 ``demos.demo5_multi_agent`` + 真实 RAG / web_search / echarts。
"""
from __future__ import annotations

import os

import pytest
from demos.demo5_multi_agent import Demo5MultiAgent

from tests.e2e_real.report import E2ERunResult, make_run_result

pytestmark = pytest.mark.skipif(
    os.environ.get("KIVI_RUN_E2E") != "1",
    reason="KIVI_RUN_E2E != 1; set KIVI_RUN_E2E=1 to run real LLM e2e",
)


# 拼装单次 E2ERunResult（agent: package-e2e-real-w82）
def _build_result(
    duration_seconds: float, success: bool, summary: str, error: str | None
) -> E2ERunResult:
    """从 demo 结果构造标准 E2ERunResult。"""
    from tests.e2e_real.conftest import resolve_provider_name  # noqa: PLC0415

    return make_run_result(
        provider=resolve_provider_name(),
        model=os.environ.get("KIVI_LLM_DEFAULT_MODEL", "claude-sonnet-4-6"),
        case_id="demo5_multi_agent",
        case_name="综合多能力：4 agent 协作",
        duration_seconds=duration_seconds,
        input_tokens=0,
        output_tokens=0,
        success=success,
        output_preview=summary,
        error=error,
    )


# Demo 5 真实 LLM 跑通（agent: package-e2e-real-w82）
async def test_demo5_multi_agent_e2e(e2e_report) -> None:
    """跑 ``Demo5MultiAgent`` + 记录 E2ERunResult。"""
    async with Demo5MultiAgent() as demo:
        result = await demo.execute()

    e2e_report.add(
        _build_result(
            duration_seconds=result.duration_seconds,
            success=result.status == "passed",
            summary=result.summary,
            error=result.error,
        )
    )
    assert result.status in ("passed", "failed"), result.summary
