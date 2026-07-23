"""kivi-eval CLI（agent: package-eval-dataset-v51）。

# eval.py（agent: package-eval-dataset-v51）
WT-G1 CLI：批量跑评测 + 汇总结果。
- run: 加载 JSONL 数据集 → 批量跑 EvalRunner → 写 JSONL 结果
- summary: 读 JSONL 结果 → 打印成功/总数 + 通过率

设计要点：
- 独立 CLI 入口（不挂 kivi 子命令；WT-G5 集成期挂入主 CLI）
- 路径遍历保护由 EvalDataset.load() 接管（CLI 不重复校验）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from kivi_agent.eval.dataset import EvalDataset
from kivi_agent.eval.judge import judge_case
from kivi_agent.eval.runner import EvalRunner


# 跑评测子命令（agent: package-eval-dataset-v51）
def cmd_run(args: argparse.Namespace) -> int:
    """跑评测子命令：加载数据集 → 批量跑 → Judge → 写 JSONL。"""
    dataset = EvalDataset.load(Path(args.dataset))
    if args.tag:
        dataset = dataset.filter(args.tag)
    if not dataset.cases:
        print(f"warning: dataset {args.dataset} has 0 cases after filter", file=sys.stderr)
        return 0

    print(f"Running {len(dataset.cases)} cases from {args.dataset}...")
    runner = EvalRunner(concurrency=args.concurrency)
    results = asyncio.run(runner.run_dataset(dataset))

    # Judge（仅对有 expected_answer 的 case 打分）
    judged = 0
    for case, result in zip(dataset.cases, results, strict=True):
        if case.expected_answer:
            result.judge_score, result.judge_reason = judge_case(case, result)
            judged += 1

    # 写 JSONL 结果（每行一个 EvalResult）
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")
    print(f"Wrote {len(results)} results ({judged} judged) to {output}")
    return 0


# 汇总评测结果子命令（agent: package-eval-dataset-v51）
def cmd_summary(args: argparse.Namespace) -> int:
    """汇总子命令：读 JSONL 结果 → 打印通过率。"""
    results: list[dict[str, Any]] = []
    with open(args.results) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))

    if not results:
        print("no results to summarize", file=sys.stderr)
        return 1

    total = len(results)
    success = sum(1 for r in results if bool(r.get("success")))
    judged = [r for r in results if r.get("judge_score") is not None]
    avg_score = (
        sum(float(r["judge_score"] or 0.0) for r in judged) / len(judged)
        if judged
        else 0.0
    )
    print(
        f"Summary: {success}/{total} succeeded ({success / total * 100:.1f}%); "
        f"judge avg={avg_score:.2f} ({len(judged)} judged)"
    )
    return 0


# 解析参数并分发到子命令（agent: package-eval-dataset-v51）
def main() -> int:
    """CLI 主入口：argparse 解析 → 调对应子命令。"""
    parser = argparse.ArgumentParser(prog="kivi-eval", description="kivi-eval CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run 子命令
    p_run = sub.add_parser("run", help="run evaluation dataset")
    p_run.add_argument("--dataset", required=True, help="path to JSONL dataset")
    p_run.add_argument("--output", default="eval-results.jsonl", help="path to write results")
    p_run.add_argument("--tag", default=None, help="filter dataset by tag")
    p_run.add_argument("--concurrency", type=int, default=4, help="concurrent case count")
    p_run.set_defaults(func=cmd_run)

    # summary 子命令
    p_sum = sub.add_parser("summary", help="summarize eval results")
    p_sum.add_argument("--results", required=True, help="path to JSONL results file")
    p_sum.set_defaults(func=cmd_summary)

    args = parser.parse_args()
    return int(args.func(args))


# 支持 `python -m kivi_agent.cli.eval run ...` 直接调用
if __name__ == "__main__":
    sys.exit(main())
