"""TeamRunner：team 数据集批量运行器（agent: package-eval-team-v52）。

# team_runner.py（agent: package-eval-team-v52）
- 复用 Wave 5.1 EvalRunner 的设计：asyncio.gather + Semaphore + 失败隔离
- run_case(case) -> TeamEvalResult：单 case 委派 team_executor.execute_case
- run_dataset(dataset) -> list[TeamEvalResult]：并发跑全集，单 case 异常转失败结果
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from kivi_agent.eval.result import CaseEvent
from kivi_agent.eval.team.models import TeamCase, TeamDataset, TeamEvalResult
from kivi_agent.eval.team.team_executor import _LlmLike, execute_case


# team 评测运行器（agent: package-eval-team-v52）
class TeamRunner:
    """team 评测运行器（asyncio + Semaphore）。

    参数：
    - concurrency：并发上限（默认 4）
    - llm_provider：满足 chat() 协议的对象；None 时 executor 跳过 LLM 调用
    """

    # 初始化并发上限与 LLM 替身
    def __init__(
        self,
        *,
        concurrency: int = 4,
        llm_provider: _LlmLike | None = None,
    ) -> None:
        self._concurrency = concurrency
        self._llm_provider = llm_provider

    # 设置 / 替换 LLM 替身（用于同一 runner 跨 case 复用）
    def bind_llm(self, llm_provider: _LlmLike | None) -> None:
        """绑定或替换 LLM 替身。"""
        self._llm_provider = llm_provider

    # 跑单个 team case
    async def run_case(self, case: TeamCase) -> TeamEvalResult:
        """跑单个 case；返回 TeamEvalResult（mock 版委派 team_executor）。"""
        return await execute_case(case, self._llm_provider)

    # 并发跑整个 team 数据集
    async def run_dataset(self, dataset: TeamDataset) -> list[TeamEvalResult]:
        """并发跑整个 team 数据集；返回与 cases 等长的结果列表（顺序保持）。

        失败隔离：单 case 异常会被转成 success=False 的 TeamEvalResult（含
        error 字段 + team.finished 事件），不会阻塞其他 case。
        """
        sem = asyncio.Semaphore(self._concurrency)

        # 并发执行单 case 并把异常转换为失败结果
        async def _run_with_sem(case: TeamCase) -> TeamEvalResult:
            async with sem:
                try:
                    return await self.run_case(case)
                except Exception as exc:  # noqa: BLE001
                    now = datetime.now(UTC).isoformat()
                    return TeamEvalResult(
                        team_id=f"team-{uuid.uuid4().hex[:8]}",
                        goal=case.goal,
                        finished_at=now,
                        success=False,
                        error=str(exc),
                        events=[
                            CaseEvent(
                                type="team.finished",
                                ts=now,
                                data={
                                    "success": False,
                                    "error": str(exc),
                                    "case_id": case.id,
                                },
                            )
                        ],
                    )

        return list(
            await asyncio.gather(*[_run_with_sem(c) for c in dataset.cases])
        )
