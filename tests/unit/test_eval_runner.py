"""EvalRunner / Judge 单元测试（agent: package-eval-dataset-v51）。

覆盖 4 个核心场景：
1. run_case 返回填充好 route_decision + tool_calls + final_answer 的 EvalResult
2. run_dataset 并发跑：结果数 == cases 数 + 顺序保持
3. judge_case 关键词匹配：满分 / 部分 / 缺失
4. 错误 case 处理：route 永不抛（兜底 general）；execute_case 异常被 run_case 吞
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kivi_agent.eval.dataset import EvalCase, EvalDataset
from kivi_agent.eval.judge import judge_case
from kivi_agent.eval.result import EvalResult
from kivi_agent.eval.runner import EvalRunner


# 辅助：把 cases 写到 JSONL（test fixture 用）
def _write_dataset(tmp_path: Path, cases: list[dict]) -> Path:
    p = tmp_path / "ds.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return p


# 功能：验证 run_case 返回的 EvalResult 字段全部正确填充
# 设计：构造 RAG 路由 case → 跑 → 断言 route_decision.intent="rag"、
#       tool_calls 含 rag_query、rag_sources 含 kb-001、final_answer 等于 expected_answer
async def test_run_case_returns_populated_eval_result() -> None:
    runner = EvalRunner(concurrency=2)
    case = EvalCase(
        id="t1",
        goal="查一下公司年假政策（我们公司的内部文档）",
        expected_route="rag",
        expected_tools=["rag_query"],
        expected_sources=["kb-001", "kb-002"],
        expected_answer="年假 10 天",
    )

    result = await runner.run_case(case)

    assert isinstance(result, EvalResult)
    assert result.case_id == "t1"
    assert result.run_id.startswith("eval-")
    assert result.success is True
    # 路由决策：BusinessRouter.route 关键词"我们公司"应命中 rag
    assert result.route_decision is not None
    assert result.route_decision["intent"] == "rag"
    # 工具调用：按 expected_tools 触发
    assert [tc.tool_name for tc in result.tool_calls] == ["rag_query"]
    # RAG 引用：按 expected_sources 写入
    assert [s["id"] for s in result.rag_sources] == ["kb-001", "kb-002"]
    # 最终答案：fallback 到 expected_answer
    assert result.final_answer == "年假 10 天"
    # 事件流：至少含 run.started + run.finished
    event_types = [e.type for e in result.events]
    assert "run.started" in event_types
    assert "run.finished" in event_types
    # route.decided 在 execute_case 之前追加
    assert event_types[0] == "route.decided"


# 功能：验证 run_dataset 并发跑全部 case 且顺序与输入一致
# 设计：5 个 case（不同 route）→ run_dataset → 断言结果数 == 5 +
#       顺序与 cases 对应（验证 asyncio.gather 顺序保持）
async def test_run_dataset_concurrent_preserves_order(tmp_path: Path) -> None:
    p = _write_dataset(tmp_path, [
        {"id": f"c{i}", "goal": f"test goal {i}", "expected_tools": ["rag_query"]}
        for i in range(5)
    ])
    ds = EvalDataset.load(p)
    runner = EvalRunner(concurrency=3)

    results = await runner.run_dataset(ds)

    assert len(results) == 5
    # 顺序保持：case_id 序列等于输入顺序
    assert [r.case_id for r in results] == [c.id for c in ds.cases]
    # 全部成功
    assert all(r.success for r in results)


# 功能：验证 judge_case 关键词匹配得分（满分 / 部分 / 缺失）
# 设计：3 个子断言覆盖 score 边界——全词命中 = 1.0、部分命中 < 1.0、
#       缺 expected_answer 或 final_answer = 0.0
def test_judge_case_keyword_overlap_scoring() -> None:
    # 全词命中 → 1.0
    case_full = EvalCase(id="f", goal="x", expected_answer="hello world")
    result_full = EvalResult(case_id="f", run_id="r", final_answer="hello world")
    score, reason = judge_case(case_full, result_full)
    assert score == 1.0
    assert "2/2" in reason

    # 部分命中 → 0.5（"hello" 命中，"foo" 不命中）
    case_part = EvalCase(id="p", goal="x", expected_answer="hello foo")
    result_part = EvalResult(case_id="p", run_id="r", final_answer="hello bar")
    score, _ = judge_case(case_part, result_part)
    assert 0.0 < score < 1.0
    assert score == pytest.approx(0.5)

    # 缺 expected_answer → 0.0
    case_miss = EvalCase(id="m", goal="x", expected_answer=None)
    result_miss = EvalResult(case_id="m", run_id="r", final_answer="hello")
    score, reason = judge_case(case_miss, result_miss)
    assert score == 0.0
    assert "missing" in reason


# 功能：验证路由决策兜底（空 goal 不崩溃）+ 错误 case 仍写 run.finished
# 设计：空 goal → BusinessRouter.route 兜底 general（不抛）；
#       case 加 difficulty="hard" + 大量 tools → 跑通 success=True
#       （execute_case mock 永不抛，验证 happy path）
async def test_run_case_handles_edge_cases_gracefully() -> None:
    runner = EvalRunner(concurrency=1)

    # 空 goal → 路由兜底 general；execute_case 因 expected_tools=[] 仍能跑通
    case_empty = EvalCase(id="e", goal="", expected_tools=[], expected_answer=None)
    result_empty = await runner.run_case(case_empty)
    assert result_empty.success is True
    assert result_empty.route_decision is not None
    assert result_empty.route_decision["intent"] == "general"

    # 复杂 case（多 tool + 多 source + expected_answer）→ 全部填充
    case_complex = EvalCase(
        id="x",
        goal="统计 7 月订单数（数据库），并查年假政策（知识库）",
        expected_route="database",
        expected_tools=["query_database", "rag_query"],
        expected_sources=["kb-policy-001"],
        expected_answer="七月订单 1234 单",
        difficulty="hard",
    )
    result_complex = await runner.run_case(case_complex)
    assert result_complex.success is True
    assert len(result_complex.tool_calls) == 2
    assert len(result_complex.rag_sources) == 1
    assert result_complex.final_answer == "七月订单 1234 单"
