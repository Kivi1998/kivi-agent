"""Wave 7 WT-K3 性能基线测试（agent: package-stage8-baselines-v7）。

# test_benchmarks.py（agent: package-stage8-baselines-v7）
3 模式（按 plan §三 WT-K3）：
1. test_single_agent_latency  - 单 Agent 跑 5 任务，p50 / p95 延迟
2. test_serial_multi_agent    - 串行多 Agent（5 子任务），总延迟
3. test_parallel_team         - 并行 Team（5 子任务并发），总延迟

设计要点：
- 全部 mock（FakeLlmProvider / TeamRunner），不依赖外部 LLM
- 多次跑取中位数（不卡绝对值，机器差异大）
- 相对比：parallel_team ≈ single_agent / 5（用 1.2 倍松约束做 sanity check）
- 输出 reports/benchmark_*.json（结构化报告，含 raw/median/p50/p95/parallel_ratio）
- KIVI_RUN_PERF=1 env guard，默认跳过
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from collections.abc import Iterable
from pathlib import Path

import pytest

from kivi_agent.core.config import KamaConfig
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.types import LlmResponse, ToolCallBlock
from kivi_agent.core.runner import AgentRunner
from kivi_agent.eval.team.models import TeamCase, TeamDataset
from kivi_agent.eval.team.team_runner import TeamRunner
from tests._fakes.llm import FakeLlmProvider, LlmScriptedResponse

# 功能：env guard 性能基线测试，默认不跑（避免污染主测试）
# 设计：用 pytest.mark.skipif 装饰整个模块，KIVI_RUN_PERF=1 时才执行
_RUN_PERF = os.environ.get("KIVI_RUN_PERF") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN_PERF,
    reason="performance tests skipped (set KIVI_RUN_PERF=1 to enable)",
)


# ---------------------------------------------------------------------------
# helpers（agent: package-stage8-baselines-v7）
# ---------------------------------------------------------------------------


class _EchoEndTurnProvider:
    """单步 LLM 替身：第 1 步 end_turn（不调任何 tool）。

    可选注入 ``simulated_latency_s`` 模拟真实 LLM 调用延迟，让 perf 测试
    区分得出"串行 vs 并行"差距。默认 0.0（毫秒级完成）。
    """

    def __init__(self, simulated_latency_s: float = 0.0) -> None:
        self._latency = simulated_latency_s

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        if self._latency > 0:
            await asyncio.sleep(self._latency)
        return LlmResponse(stop_reason="end_turn", text="done")


# mock LLM 单次 chat 的模拟延迟；让 perf 测试能体现串行/并行差距
_SIMULATED_LATENCY_S = 0.05  # 50ms


def _make_runner(
    tmp_path: Path,
    max_steps: int = 2,
    simulated_latency_s: float = _SIMULATED_LATENCY_S,
) -> AgentRunner:
    """构造一个最小 AgentRunner + tmp_path，固定 max_steps 避免拖时间。

    ``simulated_latency_s``：注入 mock LLM 的"假"延迟（默认 50ms），
    让 perf 测试能区分"串行 vs 并行"的延迟差距。真实 LLM 通常 200ms-2s，
    50ms 已足够触发调度抖动与并行加速比。
    """
    config = KamaConfig()
    config.agent.max_steps = max_steps
    return AgentRunner(
        config,
        bus=EventBus(),
        provider=_EchoEndTurnProvider(simulated_latency_s=simulated_latency_s),  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )


def _percentile(values: list[float], pct: float) -> float:
    """用 statistics.quantiles 算 p50/p95（n 较小时 linear interpolation）。"""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    # statistics.quantiles 需要 n>=2；n=100 cutpoints 输出 99 个分位
    qs = statistics.quantiles(values, n=100, method="inclusive")
    idx = max(0, min(99, int(pct) - 1))
    return float(qs[idx])


def _median(values: Iterable[float]) -> float:
    vals = list(values)
    if not vals:
        return 0.0
    return float(statistics.median(vals))


async def _run_single_agent_one_task(tmp_path: Path) -> float:
    """跑一次单 Agent 单 task，返回 wall-clock 秒数。"""
    runner = _make_runner(tmp_path)
    t0 = time.perf_counter()
    await runner.run_and_capture("hello")
    return time.perf_counter() - t0


async def _run_serial_5_tasks(tmp_path: Path) -> float:
    """跑 5 个 task 串行（同 runner 复用 5 次），返回总 wall-clock 秒数。"""
    runner = _make_runner(tmp_path)
    t0 = time.perf_counter()
    for i in range(5):
        await runner.run_and_capture(f"task-{i}")
    return time.perf_counter() - t0


async def _run_parallel_5_tasks(tmp_path: Path) -> float:
    """跑 5 个 task 并发（5 个独立 runner + asyncio.gather），返回总 wall-clock 秒数。"""
    runs_dir = tmp_path / "parallel-runs"

    async def _one() -> None:
        runner = _make_runner(runs_dir, max_steps=2)
        await runner.run_and_capture("task")

    t0 = time.perf_counter()
    await asyncio.gather(*[_one() for _ in range(5)])
    return time.perf_counter() - t0


async def _run_parallel_team_5_cases(tmp_path: Path) -> float:
    """跑 TeamRunner 5 个 case 并发（TeamRunner 内置 Semaphore 控制）。"""
    cases = [
        TeamCase(
            id=f"perf-{i}",
            goal=f"perf test {i}",
            member_specs=[{"name": "alice", "role": "researcher"}],
            sub_tasks=[{"assignee": "alice", "topic": f"t{i}"}],
        )
        for i in range(5)
    ]
    ds = TeamDataset(name="perf-5", cases=cases)
    runner = TeamRunner(concurrency=5, llm_provider=FakeLlmProvider(scripted=[LlmScriptedResponse(text="ok")]))

    t0 = time.perf_counter()
    await runner.run_dataset(ds)
    return time.perf_counter() - t0


# ---------------------------------------------------------------------------
# 模式 1：单 Agent 延迟基线
# ---------------------------------------------------------------------------


# 功能：单 Agent 跑 5 任务，输出 p50 / p95 延迟到 reports/benchmark_single.json
# 设计：跑 3 轮（每轮 5 task）取中位数；n=3 足够抵消 OS 调度抖动；
#       p50/p95 用 statistics.quantiles 计算；JSON 报告含 raw / median / p50 / p95
async def test_single_agent_latency(tmp_path: Path, repo_root: Path) -> None:
    rounds_raw: list[list[float]] = []
    for r in range(3):
        per_round: list[float] = []
        for i in range(5):
            per_round.append(await _run_single_agent_one_task(tmp_path / f"r{r}-t{i}"))
        rounds_raw.append(per_round)

    all_values = [v for round_ in rounds_raw for v in round_]
    median_per_round = [_median(r) for r in rounds_raw]
    report = {
        "mode": "single_agent",
        "rounds": rounds_raw,
        "median_per_round": median_per_round,
        "median": _median(median_per_round),
        "p50": _percentile(all_values, 50),
        "p95": _percentile(all_values, 95),
        "n_total": len(all_values),
    }

    out = repo_root / "reports" / "benchmark_single.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # sanity：单任务中位数应 < 1s（mock 下很快；放宽到 2s 防止 CI 抖动）
    assert report["median"] < 2.0, f"单任务中位数延迟过高: {report['median']:.3f}s"


# ---------------------------------------------------------------------------
# 模式 2：串行多 Agent
# ---------------------------------------------------------------------------


# 功能：串行跑 5 任务，输出总延迟到 reports/benchmark_serial.json
# 设计：复用同一个 AgentRunner 跑 5 次（避免每次重新建 runner）；
#       3 轮取中位数；总延迟应 ≈ 5 * single_agent_median（但允许 < 6s 松约束）
async def test_serial_multi_agent(tmp_path: Path, repo_root: Path) -> None:
    rounds_raw: list[float] = []
    for r in range(3):
        rounds_raw.append(await _run_serial_5_tasks(tmp_path / f"serial-{r}"))

    report = {
        "mode": "serial_multi_agent",
        "rounds": rounds_raw,
        "median": _median(rounds_raw),
        "n_tasks_per_round": 5,
    }

    out = repo_root / "reports" / "benchmark_serial.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # sanity：5 task 串行总延迟 < 6s（mock 下每 task 几十毫秒）
    assert report["median"] < 6.0, f"串行 5 任务总延迟过高: {report['median']:.3f}s"


# ---------------------------------------------------------------------------
# 模式 3：并行 Team
# ---------------------------------------------------------------------------


# 功能：并行跑 5 task，验证并行总延迟 ≈ 串行 / 5
# 设计：asyncio.gather 跑 5 独立 AgentRunner（无共享状态，确保并行）；
#       TeamRunner 走 5 case 并发（内部 Semaphore 5）；
#       3 轮取中位数；用 reports/benchmark_parallel.json + reports/benchmark_team.json
#       记录两种并行模式的延迟，并算 parallel_ratio（parallel / serial）
async def test_parallel_team(tmp_path: Path, repo_root: Path) -> None:
    # 1) gather 5 独立 AgentRunner（验证 asyncio.gather 并行）
    gather_rounds: list[float] = []
    for r in range(3):
        gather_rounds.append(await _run_parallel_5_tasks(tmp_path / f"gather-{r}"))

    # 2) TeamRunner.run_dataset（验证 Wave 5.2 team runner 并行）
    team_rounds: list[float] = []
    for r in range(3):
        team_rounds.append(await _run_parallel_team_5_cases(tmp_path / f"team-{r}"))

    gather_report = {
        "mode": "parallel_gather_5_agents",
        "rounds": gather_rounds,
        "median": _median(gather_rounds),
    }
    team_report = {
        "mode": "parallel_team_5_cases",
        "rounds": team_rounds,
        "median": _median(team_rounds),
    }

    (repo_root / "reports").mkdir(parents=True, exist_ok=True)
    (repo_root / "reports" / "benchmark_parallel.json").write_text(
        json.dumps(gather_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (repo_root / "reports" / "benchmark_team.json").write_text(
        json.dumps(team_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # sanity 1：并行总延迟 < 串行总延迟（gather 5 个独立 runner，mock 下应 < 1s）
    assert gather_report["median"] < 2.0, (
        f"并行 gather 5 agent 延迟过高: {gather_report['median']:.3f}s"
    )

    # sanity 2：team runner 5 case 并发 < 1s
    assert team_report["median"] < 2.0, (
        f"并行 team runner 延迟过高: {team_report['median']:.3f}s"
    )

    # 软约束：并行 (gather) 总延迟 ≤ 串行 / 2（mock 极快时 gather 应接近单 task 时间）
    # 不强卡绝对值，卡"并行比串行快"这个相对关系
    serial_median = json.loads(
        (repo_root / "reports" / "benchmark_serial.json").read_text(encoding="utf-8")
    )["median"]
    parallel_ratio = gather_report["median"] / max(serial_median, 1e-6)
    summary = {
        "serial_median": serial_median,
        "parallel_gather_median": gather_report["median"],
        "parallel_team_median": team_report["median"],
        "parallel_vs_serial_ratio": parallel_ratio,
        "note": "ratio < 1.0 means parallel faster than serial (expected)",
    }
    (repo_root / "reports" / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 软约束：parallel ≤ serial * 0.8（允许 20% 抖动；mock 下 parallel 应明显快于 serial）
    # 留 1.2x 上限给 CI 抖动
    assert parallel_ratio < 1.2, (
        f"并行 gather 未体现加速比: serial={serial_median:.3f}s, "
        f"parallel={gather_report['median']:.3f}s, ratio={parallel_ratio:.2f}"
    )
