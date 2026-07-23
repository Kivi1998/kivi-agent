"""team_executor：单 team case 执行器（agent: package-eval-team-v52）。

# team_executor.py（agent: package-eval-team-v52）
- execute_case(case, llm_provider) -> TeamEvalResult
- mock 版执行器：按 case.sub_tasks 委派给成员，调用 LLM 跑一步
- 与 Wave 5.1 runner_executor.execute_case 设计对齐：mock + 事件流 + 汇总统计
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from kivi_agent.eval.result import CaseEvent
from kivi_agent.eval.team.mailbox_tracker import MailboxTracker
from kivi_agent.eval.team.models import (
    DelegationStep,
    MemberOutcome,
    TeamCase,
    TeamEvalResult,
)

if TYPE_CHECKING:
    pass


from kivi_agent.core.events.bus import EventBus


# LLMProvider 协议（与 kivi_agent.core.llm.base.LLMProvider 对齐）
# 在 team 评测场景下不直接 import core.llm 以避免循环依赖风险
class _LlmLike(Protocol):
    """FakeLlmProvider / 真实 LLMProvider 都满足的最小接口。"""

    async def chat(  # noqa: D401 - Protocol 简写
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> Any: ...


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# NoopBus：满足 EventBus.publish 协议；不消费事件，用于 executor 的 LLM 调用
class _NoopBus:
    """最小 EventBus 替身：publish 立即返回。"""

    # 吞掉事件
    async def publish(self, event: Any) -> None:  # noqa: D401
        return None


# 执行单 team case（agent: package-eval-team-v52）
async def execute_case(
    case: TeamCase,
    llm_provider: _LlmLike | None = None,
    *,
    bus: EventBus | None = None,
) -> TeamEvalResult:
    """执行单 team case（mock 版）；返回 TeamEvalResult。

    流程：
    1. 构造 team_id + MemberOutcome 列表（每个 member_spec 一条）
    2. team.created 事件入列
    3. 按 case.sub_tasks 委派：每个 sub_task 生成一条 DelegationStep，
       增加目标成员的 steps / tool_calls_count，写 team.member_dispatched 事件
    4. 调一次 LLM（per sub_task）以满足"LLM 介入"接口；LLM 异常被吞，不阻塞
    5. 每个成员做一次 mailbox 消费；用 MailboxTracker 累加 total/successful
    6. 汇总 planned_assignments / actual_assignments
    7. 写 team.finished 事件；设置 success = all(member.success)

    LLM 异常处理：单次 LLM 失败不阻塞 team；其他 case / 其他 member 正常推进。
    """
    team_id = f"team-{uuid.uuid4().hex[:8]}"
    started_at = _now_iso()
    result = TeamEvalResult(
        team_id=team_id,
        goal=case.goal,
        started_at=started_at,
    )
    tracker = MailboxTracker()
    bus = bus or _NoopBus()  # type: ignore[assignment]

    # 1. team.created 事件
    result.events.append(
        CaseEvent(
            type="team.created",
            ts=started_at,
            data={
                "team_id": team_id,
                "case_id": case.id,
                "goal": case.goal,
                "members": [{"name": m.name, "role": m.role} for m in case.member_specs],
            },
        )
    )

    # 2. 初始化 member_outcomes
    member_map: dict[str, MemberOutcome] = {}
    for spec in case.member_specs:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        member = MemberOutcome(
            name=spec.name,
            role=spec.role,
            run_id=run_id,
        )
        member_map[spec.name] = member
    result.member_outcomes = list(member_map.values())

    # 3. 委派每个 sub_task
    for sub_task in case.sub_tasks:
        outcome: MemberOutcome | None = member_map.get(sub_task.assignee)
        if outcome is None:
            # 未指定有效 assignee：记一个 unassigned 事件，不计入实际委派
            result.events.append(
                CaseEvent(
                    type="team.unassigned",
                    ts=_now_iso(),
                    data={"sub_task": sub_task.topic, "assignee": sub_task.assignee},
                )
            )
            continue
        # 委派步骤入委派链 + tracker
        step = DelegationStep(
            from_member="team",
            to_member=sub_task.assignee,
            sub_task=sub_task.topic,
            ts=_now_iso(),
        )
        result.delegation_chain.append(step)
        tracker.record_write(
            recipient=sub_task.assignee,
            sender="team",
            content=sub_task.topic,
            sub_task=sub_task.topic,
        )
        # 累计成员活动
        outcome.steps += 1
        outcome.tool_calls_count += 1
        result.events.append(
            CaseEvent(
                type="team.member_dispatched",
                ts=_now_iso(),
                data={
                    "sub_task": sub_task.topic,
                    "assignee": sub_task.assignee,
                    "run_id": outcome.run_id,
                },
            )
        )
        # 4. 调一次 LLM（LLM 异常吞掉，不阻塞 executor）
        if llm_provider is not None:
            try:
                await llm_provider.chat(
                    messages=[{"role": "user", "content": sub_task.topic}],
                    tool_schemas=[],
                    bus=bus,  # type: ignore[arg-type]
                    run_id=outcome.run_id,
                    step=outcome.steps,
                )
            except Exception:  # noqa: BLE001 - LLM 异常不影响 mock 跑通
                pass

    # 5. 每个成员做一次 mailbox 消费 + 收尾
    for outcome in result.member_outcomes:
        # 模拟：该成员消费的 mailbox 消息数 = 委派给它的 sub_task 数
        per_recipient = sum(
            1 for s in result.delegation_chain if s.to_member == outcome.name
        )
        if per_recipient > 0:
            fake_messages = [
                {"sender": "team", "content": "task", "ts": _now_iso()}
                for _ in range(per_recipient)
            ]
            tracker.record_consume(recipient=outcome.name, messages=fake_messages)
            result.events.append(
                CaseEvent(
                    type="team.handoff",
                    ts=_now_iso(),
                    data={"to": outcome.name, "messages_count": per_recipient},
                )
            )
        outcome.finished_at = _now_iso()
        # 成员 success = True 条件：被委派过 + 不超过 max_steps
        outcome.success = (
            outcome.steps > 0 and outcome.steps <= case.max_steps_per_member
        )

    # 6. 汇总 planned / actual
    planned: dict[str, int] = {}
    for st in case.sub_tasks:
        planned[st.assignee] = planned.get(st.assignee, 0) + 1
    actual: dict[str, int] = {}
    for s in result.delegation_chain:
        actual[s.to_member] = actual.get(s.to_member, 0) + 1
    result.planned_assignments = planned
    result.actual_assignments = actual

    # 把 tracker 的委派链 + 计数同步到 result
    result.delegation_chain = list(tracker.delegation_chain)
    result.total_messages = tracker.total_messages
    result.successful_messages = tracker.successful_messages

    # 7. 汇总：team 成功 = 全部成员成功 且 至少有一个委派
    result.success = bool(result.member_outcomes) and all(
        o.success for o in result.member_outcomes
    )
    result.finished_at = _now_iso()
    result.events.append(
        CaseEvent(
            type="team.finished",
            ts=result.finished_at,
            data={
                "team_id": team_id,
                "case_id": case.id,
                "success": result.success,
                "member_count": len(result.member_outcomes),
                "delegations": len(result.delegation_chain),
            },
        )
    )
    return result
