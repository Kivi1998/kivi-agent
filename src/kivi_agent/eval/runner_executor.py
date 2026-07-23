"""case 执行器（agent: package-eval-dataset-v51）。

模拟 AgentRuntime 行为：按路由决策触发对应业务 Tool，收集事件 + token。
完整 AgentRuntime 集成（core/runner.AgentRunner.run_and_capture）留 WT-G3 集成期。
"""

from __future__ import annotations

import time

from kivi_agent.eval.dataset import EvalCase
from kivi_agent.eval.result import CaseEvent, EvalResult, ToolCallRecord


# 当前时间戳（ISO 8601 简化版；不强制微秒精度）
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# 执行单 case（agent: package-eval-dataset-v51）
async def execute_case(
    case: EvalCase,
    result: EvalResult,
    token_pricing: dict[str, tuple[float, float]],
) -> None:
    """执行单 case（mock 版）。

    流程（与 WT-G1 plan §三 一致）：
    1. 按 case.expected_tools 顺序触发 mock tool 调用
    2. 按 case.expected_sources 生成 mock RAG sources
    3. 模拟 token 用量（默认 100 in + 50 out）
    4. 填充 final_answer（fallback 到 expected_answer）
    5. 写 run.finished 事件

    完整 AgentRuntime 集成（core/runner.AgentRunner.run_and_capture + EventBus 订阅）
    留 WT-G3 集成期；本函数保证数据通路打通的正确性，便于 G2/G3 拿真实数据。
    """
    started = time.time()
    result.events.append(
        CaseEvent(
            type="run.started",
            ts=_now_iso(),
            data={"case_id": case.id, "goal": case.goal},
        )
    )

    # 1. 模拟 tool 调用（按 expected_tools 顺序）
    for tool_name in case.expected_tools:
        result.tool_calls.append(
            ToolCallRecord(
                tool_name=tool_name,
                started_at=_now_iso(),
                success=True,
            )
        )
        result.events.append(
            CaseEvent(
                type="tool.call_started",
                ts=_now_iso(),
                data={"tool_name": tool_name, "case_id": case.id},
            )
        )
        result.events.append(
            CaseEvent(
                type="tool.call_finished",
                ts=_now_iso(),
                data={"tool_name": tool_name, "success": True},
            )
        )

    # 2. 模拟 RAG 引用（按 expected_sources）
    for src in case.expected_sources:
        result.rag_sources.append(
            {
                "id": src,
                "title": f"doc-{src}",
                "snippet": f"Mock snippet for {src}",
                "score": 0.9,
            }
        )
    if case.expected_sources:
        result.events.append(
            CaseEvent(
                type="rag.sources_cited",
                ts=_now_iso(),
                data={"sources": list(case.expected_sources), "case_id": case.id},
            )
        )

    # 3. 模拟 token 用量（演示版固定值；WT-G3 改用真实 LLM usage）
    result.input_tokens = 100
    result.output_tokens = 50
    result.cache_read_tokens = 0

    # 4. 模拟 final_answer（fallback 顺序：expected_answer → mock 默认）
    result.final_answer = case.expected_answer or f"Mock answer for goal: {case.goal}"

    # 5. 写 run.finished
    elapsed = time.time() - started
    result.events.append(
        CaseEvent(
            type="run.finished",
            ts=_now_iso(),
            data={"success": True, "elapsed_s": elapsed, "case_id": case.id},
        )
    )
    result.success = True
    result.finished_at = _now_iso()

    # 避免 token_pricing 形参的 mypy 警告（保留参数为 WT-G3 真实成本计算接口）
    _ = token_pricing
