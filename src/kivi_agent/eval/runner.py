"""批量评测运行器（agent: package-eval-dataset-v51）。

复用 Wave 1 既有 AgentRuntime + BusinessRouter + 6 业务 Tool。
Wave 4 真实服务 Adapter 透明接入（Mock 默认；RAG_MODE=http / DB_MODE=sqlite 自动启用）。

设计要点（与 WT-G1 plan §三 一致）：
- 复用 BusinessRouter.route() 拿 RouteDecision（v1 §3 intent 分类）
- 单 case 委派 runner_executor.execute_case()（mock 版）
- asyncio.Semaphore 控制并发
- 价格表留接口位（WT-G3 真实 LLM cost 用）
"""

from __future__ import annotations

import asyncio
import time
import uuid

from kivi_agent.core.agents.business_router import BusinessRouter
from kivi_agent.eval.dataset import EvalCase, EvalDataset
from kivi_agent.eval.result import CaseEvent, EvalResult
from kivi_agent.eval.runner_executor import execute_case

# 模型 token 单价表（每 1k token 的美元价格，agent: package-eval-dataset-v51）
# (input_price_per_1k, output_price_per_1k)
DEFAULT_TOKEN_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5": (0.0008, 0.004),
    "gpt-4o": (0.005, 0.015),
}


# 单进程批量评测运行器（agent: package-eval-dataset-v51）
class EvalRunner:
    """单进程批量评测运行器。

    参数：
        concurrency: 同时跑的 case 数（默认 4；CPU 密集型可降到 2）
        token_pricing: 模型 token 单价表；用于 WT-G3 真实成本计算
    """

    def __init__(
        self,
        *,
        concurrency: int = 4,
        token_pricing: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        self._router = BusinessRouter()
        self._concurrency = concurrency
        self._token_pricing: dict[str, tuple[float, float]] = (
            token_pricing if token_pricing is not None else dict(DEFAULT_TOKEN_PRICING)
        )

    # 跑单个 case（agent: package-eval-dataset-v51）
    async def run_case(self, case: EvalCase) -> EvalResult:
        """跑单个 case；返回 EvalResult。

        流程：
        1. 路由决策（BusinessRouter.route）→ 写入 route_decision + 事件
        2. 执行 case（runner_executor.execute_case）→ 写 tool_calls / events /
           rag_sources / tokens / final_answer
        """
        run_id = f"eval-{uuid.uuid4().hex[:8]}"
        result = EvalResult(case_id=case.id, run_id=run_id)

        # 1. 路由决策（复用 Wave 2 BusinessRouter）
        decision = self._router.route(case.goal)
        result.route_decision = {
            "intent": decision.intent,
            "target_profiles": list(decision.target_profiles),
            "is_multi_intent": decision.is_multi_intent,
            "confidence": decision.confidence,
            "matched_keywords": list(decision.matched_keywords),
        }
        result.events.append(
            CaseEvent(
                type="route.decided",
                ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
                data=dict(result.route_decision),
            )
        )

        # 2. 委派 case 执行（mock 版；WT-G3 换真实 AgentRuntime）
        await execute_case(case, result, self._token_pricing)
        return result

    # 批量跑整个数据集（agent: package-eval-dataset-v51）
    async def run_dataset(self, dataset: EvalDataset) -> list[EvalResult]:
        """并发跑整个数据集（asyncio.Semaphore 控制）。

        返回与 dataset.cases 等长的结果列表（顺序保持）。
        """
        sem = asyncio.Semaphore(self._concurrency)

        async def _run_with_sem(case: EvalCase) -> EvalResult:
            async with sem:
                return await self.run_case(case)

        return list(await asyncio.gather(*[_run_with_sem(c) for c in dataset.cases]))
