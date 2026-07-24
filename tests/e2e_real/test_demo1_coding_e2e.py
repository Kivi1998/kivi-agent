"""Demo 1 编程 Agent 真实 LLM 端到端（agent: package-e2e-real-w82）。

# test_demo1_coding_e2e.py（agent: package-e2e-real-w82）
Wave 8.2 WT-L3：跑 ``demos.demo1_coding`` 并记录 E2ERunResult 到
``KIVI_E2E_REPORT_DIR`` 下的 JSON + Markdown。

env guard：``KIVI_RUN_E2E != "1"`` 时整个 module skip（默认安全）。
真实 LLM provider 注入：集成期 main agent 在 ``_runtime_provider.py`` 注入
实际实现；本测试只 wrap demo 业务逻辑 + 记录结果。
"""
from __future__ import annotations

import os

import pytest
from demos.demo1_coding import Demo1Coding

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
        case_id="demo1_coding",
        case_name="编程 Agent：修复 add 函数",
        duration_seconds=duration_seconds,
        input_tokens=0,  # 真实 LLM 接入后填实际值
        output_tokens=0,
        success=success,
        output_preview=summary,
        error=error,
    )


# Demo 1 真实 LLM 跑通（agent: package-e2e-real-w82）
async def test_demo1_coding_e2e(e2e_report) -> None:
    """跑 ``Demo1Coding`` + 记录 E2ERunResult（共享 session report）。"""
    async with Demo1Coding() as demo:
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
