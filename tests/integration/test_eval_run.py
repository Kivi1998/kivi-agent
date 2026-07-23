"""EvalRunner 集成测试（agent: package-eval-dataset-v51）。

# test_eval_run.py（agent: package-eval-dataset-v51）
3 场景：
1. 10 case 数据集全跑通（含 5 种业务 Profile 路由）
2. 1 case 失败不阻塞其他 case（即使 WT-G3 切真实后有失败，整体并发仍完成）
3. 持久化结果文件：CLI run 写 JSONL → summary 读 JSONL 打印通过率
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from kivi_agent.eval.dataset import EvalCase, EvalDataset
from kivi_agent.eval.result import EvalResult
from kivi_agent.eval.runner import EvalRunner

# 10 case 测试数据集：覆盖 5 种业务 Profile（agent: package-eval-dataset-v51）
# 关键词表来自 BusinessRouter.INTENT_KEYWORDS（rag / web_search / database / general）
DEMO_CASES: list[dict] = [
    # RAG（3）
    {"id": "rag-1", "goal": "查一下我们公司年假政策", "expected_route": "rag",
     "expected_tools": ["rag_query"], "expected_sources": ["kb-001"],
     "expected_answer": "年假 10 天", "tags": ["rag"]},
    {"id": "rag-2", "goal": "FAQ 怎么申请出差", "expected_route": "rag",
     "expected_tools": ["rag_query"], "expected_sources": ["kb-002"],
     "expected_answer": "出差需要 OA 申请", "tags": ["rag"]},
    {"id": "rag-3", "goal": "内部文档里有没有 OKR 模板", "expected_route": "rag",
     "expected_tools": ["rag_query"], "expected_sources": ["kb-003"],
     "expected_answer": "OKR 模板在 kb-003", "tags": ["rag"]},
    # Web Search（2）
    {"id": "web-1", "goal": "网上搜一下最新 AI 论文", "expected_route": "web_search",
     "expected_tools": ["web_search"], "expected_answer": "最新论文列表", "tags": ["web"]},
    {"id": "web-2", "goal": "互联网新闻今天头条是什么", "expected_route": "web_search",
     "expected_tools": ["web_search"], "expected_answer": "今日新闻摘要", "tags": ["web"]},
    # Database（2）
    {"id": "db-1", "goal": "统计 7 月订单数量", "expected_route": "database",
     "expected_tools": ["query_database"], "expected_answer": "七月订单 1234 单", "tags": ["db"]},
    {"id": "db-2", "goal": "SUM 一下上周销售额", "expected_route": "database",
     "expected_tools": ["query_database"], "expected_answer": "上周销售 100 万", "tags": ["db"]},
    # General（2）
    {"id": "gen-1", "goal": "你好", "expected_route": "general",
     "expected_tools": [], "expected_answer": "你好", "tags": ["general"]},
    {"id": "gen-2", "goal": "今天天气如何", "expected_route": "general",
     "expected_tools": [], "expected_answer": "本地无天气 API", "tags": ["general"]},
    # 复杂（1：多工具）
    {"id": "mix-1", "goal": "先查数据库订单数，再查知识库退换货政策", "expected_route": "database",
     "expected_tools": ["query_database", "rag_query"],
     "expected_sources": ["kb-policy-001"], "expected_answer": "订单 1234 单可退换", "tags": ["mix"]},
]


# 写 JSONL 数据集（fixture helper）
def _write_demo_dataset(path: Path) -> Path:
    with open(path, "w", encoding="utf-8") as f:
        for c in DEMO_CASES:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return path


# 功能：验证 10 case 数据集全跑通（5 种 Profile 路由全部命中）
# 设计：用 DEMO_CASES 写 JSONL → EvalDataset.load → EvalRunner.run_dataset →
#       断言成功数 == 10、case_id 顺序保持、5 种 intent 都出现
async def test_ten_case_dataset_runs_end_to_end(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "demo.jsonl")
    ds = EvalDataset.load(p)
    assert len(ds.cases) == 10

    runner = EvalRunner(concurrency=4)
    results = await runner.run_dataset(ds)

    assert len(results) == 10
    # 全部成功（mock executor 不抛）
    assert all(r.success for r in results)
    # case_id 顺序保持
    assert [r.case_id for r in results] == [c.id for c in ds.cases]
    # 5 种 intent 全部出现（4 业务 + general）
    intents = {r.route_decision["intent"] for r in results if r.route_decision}
    assert "rag" in intents
    assert "web_search" in intents
    assert "database" in intents
    # "general" 兜底在"你好"这种无关键词 case 上
    assert "general" in intents


# 功能：验证单 case 执行失败会持久化为失败结果且不阻塞其他 case
# 设计：patch execute_case 仅让 edge-1 抛 RuntimeError，其他 10 case 调真实 mock executor；
#       断言整批 11 个结果均返回，其中 10 成功、1 失败并保留错误消息
async def test_one_failing_case_does_not_block_others(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "mixed.jsonl")
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "edge-1", "goal": "ping"}) + "\n")

    ds = EvalDataset.load(p)
    runner = EvalRunner(concurrency=2)
    from kivi_agent.eval.runner_executor import execute_case as real_execute_case

    async def _execute_with_failure(
        case: EvalCase,
        result: EvalResult,
        pricing: dict[str, tuple[float, float]],
    ) -> None:
        if case.id == "edge-1":
            raise RuntimeError("synthetic integration failure")
        await real_execute_case(case, result, pricing)

    with patch(
        "kivi_agent.eval.runner.execute_case",
        new=AsyncMock(side_effect=_execute_with_failure),
    ):
        results = await runner.run_dataset(ds)

    assert len(results) == 11
    assert sum(1 for r in results if r.success) == 10
    edge_result = next(r for r in results if r.case_id == "edge-1")
    assert edge_result.success is False
    assert edge_result.error == "synthetic integration failure"
    assert edge_result.events[-1].type == "run.finished"


# 功能：验证 CLI run 写 JSONL → CLI summary 读 JSONL 打印通过率
# 设计：用 subprocess 调 `python -m kivi_agent.cli.eval run/summary`；
#       subprocess 比 in-process 调 main() 更接近真实用户使用路径
def test_cli_persists_results_and_summary_reads_them(tmp_path: Path) -> None:
    dataset = _write_demo_dataset(tmp_path / "demo.jsonl")
    results_path = tmp_path / "results.jsonl"

    # 1. 跑 run
    run_proc = subprocess.run(
        [
            sys.executable, "-m", "kivi_agent.cli.eval", "run",
            "--dataset", str(dataset),
            "--output", str(results_path),
            "--concurrency", "2",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert run_proc.returncode == 0, f"run failed: {run_proc.stderr}"
    assert "Wrote 10 results" in run_proc.stdout

    # 2. 验证 JSONL 文件可读 + 行数 == 10
    assert results_path.exists()
    with open(results_path) as f:
        lines = [ln for ln in f if ln.strip()]
    assert len(lines) == 10
    # 每行是合法 JSON
    first = json.loads(lines[0])
    assert "case_id" in first
    assert "success" in first
    assert "judge_score" in first  # 8 个 case 有 expected_answer 故有 judge_score

    # 3. 跑 summary
    sum_proc = subprocess.run(
        [
            sys.executable, "-m", "kivi_agent.cli.eval", "summary",
            "--results", str(results_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert sum_proc.returncode == 0, f"summary failed: {sum_proc.stderr}"
    assert "10/10 succeeded" in sum_proc.stdout
    assert "judge avg" in sum_proc.stdout
