"""多 Profile 并行执行 + Synthesizer 汇总（Wave 2 B3）。

SynthesizerRunner 负责：
1. 接收 RouteDecision 拆出的 sub-profiles 列表（不含 synthesizer）
2. 用 spawn_background_subagent 并行启动每个 sub-profile（独立 run_id）
3. 订阅父 bus 上的 RagSourcesCitedEvent / ChartRenderedEvent，按 run_id 归类到对应 SubResult
4. 等所有子任务完成后，从 BackgroundTaskRegistry 拿每个 run_id 的最终文本
5. 用 synthesizer Profile 的 system_prompt 喂给 LLM，让模型去重/合并/排序/润色
6. 返回 SynthesizedResult（含 final_output / sources / charts / sub_results）

单意图场景不走此 runner（直接由 BusinessRouter 调度对应 Profile 即可）。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from kivi_agent.core.agents.loader import AgentProfile, AgentProfileLoader
from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    RagSourcesCitedEvent,
    SubagentFinishedEvent,
    SubagentStartedEvent,
)
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.base import LLMProvider
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.subagent.tool import spawn_background_subagent

if TYPE_CHECKING:
    from kivi_agent.core.permissions.manager import PermissionManager

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# 单个子 Agent 的执行结果
@dataclass
class SubResult:
    """单个子 Agent 的执行结果。

    - output: 子 Agent 产出的最终文本（来自 child_context.result）
    - citations: RAG 引用列表（每条来自 RagSourcesCitedEvent；非 rag 业务为空）
    - charts: ECharts 元数据（每条来自 ChartRenderedEvent；非 database 业务为空）
    - trace_ids: 子 run 的 trace id 列表（目前与 run_id 等价；预留扩展）
    """

    profile_name: str
    output: str = ""
    citations: list[str] = field(default_factory=list)
    charts: list[dict[str, object]] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)


# SynthesizerRunner 的最终输出
@dataclass
class SynthesizedResult:
    """合成结果。

    - final_output: synthesizer LLM 产出的最终答案文本
    - sources: (profile_name, citation) 列表——已 flatten；供 TUI 渲染引用
    - charts: ECharts 元数据列表（透传自上游 sub-results，未修改）
    - sub_results: 所有 SubResult 完整保留（用于埋点/调试）
    """

    final_output: str
    sources: list[tuple[str, str]] = field(default_factory=list)
    charts: list[dict[str, object]] = field(default_factory=list)
    sub_results: list[SubResult] = field(default_factory=list)


# 收集 sub-profile 阶段事件用的中间状态
@dataclass
class _PendingSub:
    """单次 sub-profile 启动后跟踪的中间状态。"""

    profile_name: str
    run_id: str
    citations: list[str] = field(default_factory=list)
    charts: list[dict[str, object]] = field(default_factory=list)
    finished: bool = False
    status: str = "running"  # "running" | "success" | "failed"


# 并行执行多个 sub-Profile + 用 synthesizer Profile 汇总的 runner
class SynthesizerRunner:
    """并行执行多个子 Profile + 用 synthesizer Profile 汇总。"""

    def __init__(
        self,
        provider: LLMProvider,
        bus: EventBus,
        permission_manager: PermissionManager | None,
        profile_loader: AgentProfileLoader,
        runs_dir: Path,
        session_id: str,
        *,
        max_steps: int = 10,
    ) -> None:
        self._provider = provider
        self._bus = bus
        self._permission_manager = permission_manager
        self._profile_loader = profile_loader
        self._runs_dir = runs_dir
        self._session_id = session_id
        self._max_steps = max_steps
        # sub-Profile 启动时复用同一份 task registry；runner 不负责清理
        self._task_registry = BackgroundTaskRegistry()

    # 主入口：并行执行 sub-profiles + 汇总
    async def run(
        self,
        query: str,
        sub_profiles: list[str],
        parent_run_id: str,
    ) -> SynthesizedResult:
        """执行 sub-profiles 并汇总到 synthesizer。

        - sub_profiles 必须是 sub-Profile 名列表（不含 synthesizer 本身）
        - parent_run_id 用于把子 run 关联回父 run
        """
        if not sub_profiles:
            return SynthesizedResult(
                final_output="",
                sources=[],
                charts=[],
                sub_results=[],
            )

        # 启动前预校验：每个 sub-profile 都能加载（缺失则记一个失败 SubResult 跳过启动）
        loadable: list[tuple[str, AgentProfile]] = []
        for name in sub_profiles:
            profile = self._profile_loader.load(name)
            if profile is None:
                logger.warning("synthesizer: profile not found, skipping name=%s", name)
                continue
            loadable.append((name, profile))

        # 启动前订阅 bus 事件：跟踪 citations / charts / 完成信号
        pending: dict[str, _PendingSub] = {}  # run_id → 中间状态
        started_event_for_sub: dict[str, str] = {}  # run_id → profile_name

        async def _on_event(event: object) -> None:
            if isinstance(event, SubagentStartedEvent):
                # 把 sub-agent 的 run_id 关联回 profile_name（通过 description 字段含 profile name）
                # 简化策略：description 由 spawn 时拼成 "profile:<name>"
                started_event_for_sub[event.run_id] = event.description
            elif isinstance(event, SubagentFinishedEvent):
                ps = pending.get(event.run_id)
                if ps is not None:
                    ps.finished = True
                    ps.status = event.status
            elif isinstance(event, RagSourcesCitedEvent):
                ps = pending.get(event.run_id)
                if ps is not None:
                    for src in event.sources:
                        # 序列化引用为简短字符串（文档/段落/链接）
                        if isinstance(src, dict):
                            text = str(src.get("text") or src.get("title") or src.get("url") or src)
                        else:
                            text = str(src)
                        if text and text not in ps.citations:
                            ps.citations.append(text)
            elif isinstance(event, ChartRenderedEvent):
                ps = pending.get(event.run_id)
                if ps is not None:
                    # ECharts option dict 透传
                    ps.charts.append(event.option_dict)

        self._bus.subscribe(_on_event)

        try:
            # 并行启动所有 sub-profile
            spawn_tasks: list[asyncio.Task[str]] = []
            for name, profile in loadable:
                task = asyncio.create_task(
                    spawn_background_subagent(
                        provider=self._provider,
                        parent_bus=self._bus,
                        parent_run_id=parent_run_id,
                        permission_manager=self._permission_manager,
                        max_steps=profile.max_steps or self._max_steps,
                        task_registry=self._task_registry,
                        runs_dir=self._runs_dir,
                        session_id=self._session_id,
                        depth=1,  # 业务子 agent 视为深度 1（synthesizer 自身是深度 0）
                        description=f"profile:{name}",
                        prompt=query,
                        subagent_type=name,
                    )
                )
                spawn_tasks.append(task)

            spawn_results = await asyncio.gather(*spawn_tasks, return_exceptions=True)

            # 把 spawn 出来的 run_id 填入 pending
            for (name, _profile), result in zip(loadable, spawn_results, strict=True):
                if isinstance(result, BaseException):
                    logger.error("synthesizer: spawn failed profile=%s err=%r", name, result)
                    continue
                run_id = str(result)
                pending[run_id] = _PendingSub(profile_name=name, run_id=run_id)

            # 等待所有子任务完成：监听 SubagentFinishedEvent
            await self._wait_for_completion(pending)

            # 从 task registry 拿每个 run_id 的最终 output
            sub_results = self._collect_sub_results(pending)

            # 调 LLM 合成（synthesizer Profile system_prompt + sub-results 喂给模型）
            final_output = await self._synthesize(query, sub_results)

            # 汇总 sources / charts 透传
            sources: list[tuple[str, str]] = []
            charts: list[dict[str, object]] = []
            for sr in sub_results:
                for c in sr.citations:
                    sources.append((sr.profile_name, c))
                charts.extend(sr.charts)

            return SynthesizedResult(
                final_output=final_output,
                sources=sources,
                charts=charts,
                sub_results=sub_results,
            )
        finally:
            # 注：bus.subscribe() 没有提供 unsubscribe，本 runner 是一次性使用，不污染后续订阅
            # 如果未来要复用 runner 实例，需要给 EventBus 加 unsubscribe
            pass

    # 等待所有 pending 子任务完成；使用 task 自身的 done() 状态 + 短轮询兜底
    async def _wait_for_completion(self, pending: dict[str, _PendingSub]) -> None:
        if not pending:
            return

        # 用 task 注册表查每个 run_id 的 asyncio.Task
        async def _wait_one(run_id: str) -> None:
            entry = self._task_registry.get(run_id)
            if entry is None:
                return
            task, _ctx = entry
            # 等待 task 自身完成；事件回调会标记 pending[run_id].finished
            try:
                await task
            except Exception:
                logger.exception("synthesizer: subagent task raised run_id=%s", run_id)

        await asyncio.gather(*(_wait_one(rid) for rid in list(pending.keys())))

        # 双保险：如果事件回调遗漏，给一个 100ms 缓冲
        await asyncio.sleep(0.1)

    # 从 pending 状态 + task_registry 取每个 sub-profile 的最终结果
    def _collect_sub_results(self, pending: dict[str, _PendingSub]) -> list[SubResult]:
        results: list[SubResult] = []
        for run_id, ps in pending.items():
            entry = self._task_registry.get(run_id)
            output = ""
            if entry is not None:
                _task, ctx = entry
                output = ctx.result or ""
            results.append(
                SubResult(
                    profile_name=ps.profile_name,
                    output=output,
                    citations=list(ps.citations),
                    charts=list(ps.charts),
                    trace_ids=[run_id],
                )
            )
        return results

    # 用 synthesizer Profile 喂 LLM 出最终答案
    async def _synthesize(
        self, query: str, sub_results: list[SubResult]
    ) -> str:
        """把多个 SubResult 拼成 user 消息，调 LLM 出最终答案。"""
        synth_profile = self._profile_loader.load("synthesizer")
        system_prompt = (
            synth_profile.system_prompt
            if synth_profile is not None
            else "You are a synthesizer that merges multiple sub-agent results."
        )

        # 拼接 sub-results 为结构化文本（LLM 友好）
        if sub_results:
            sub_text_parts: list[str] = []
            for i, sr in enumerate(sub_results, 1):
                citations_str = (
                    "\n".join(f"  - {c}" for c in sr.citations) if sr.citations else "  (none)"
                )
                charts_str = (
                    "\n".join(f"  - {c}" for c in sr.charts) if sr.charts else "  (none)"
                )
                sub_text_parts.append(
                    f"[SubResult {i}] profile={sr.profile_name}\n"
                    f"Output:\n{sr.output or '(empty)'}\n"
                    f"Citations:\n{citations_str}\n"
                    f"Charts:\n{charts_str}\n"
                )
            sub_text = "\n---\n".join(sub_text_parts)
        else:
            sub_text = "(no sub-results)"

        user_msg = (
            f"## Original Query\n{query}\n\n"
            f"## Sub-Agent Results\n{sub_text}\n\n"
            f"## Task\n"
            f"Merge the sub-agent results into a single final answer. "
            f"Preserve all citations and chart metadata from upstream. "
            f"Reply in the same language as the original query."
        )

        # 调 LLM（不传 tool schema——synthesizer 不应再调业务 Tool）
        response = await self._provider.chat(
            messages=[{"role": "user", "content": user_msg}],
            tool_schemas=[],
            bus=self._bus,
            run_id=f"synth-{_now()}",
            step=0,
            system=system_prompt,
        )
        return response.text
