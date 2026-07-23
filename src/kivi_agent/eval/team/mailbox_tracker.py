"""MailboxTracker：监听 mailbox 写消费 → 委派链 + handoff 事件（agent: package-eval-team-v52）。

# mailbox_tracker.py（agent: package-eval-team-v52）
- record_write(recipient, sender, content, sub_task)：push 一条 DelegationStep
- record_consume(recipient, messages)：累加 successful_messages + total_messages
- 与 core/teams/mailbox.py 的 write_message / consume_messages 配套使用
"""

from __future__ import annotations

from datetime import UTC, datetime

from kivi_agent.eval.result import CaseEvent
from kivi_agent.eval.team.models import DelegationStep, TeamEvalResult


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# 跟踪 mailbox 写消费：team 委派链 + handoff 计数（agent: package-eval-team-v52）
class MailboxTracker:
    """Mailbox 写消费监听器。

    使用模式：
    - team_create 时初始化 tracker
    - 每次 team_message 写入：tracker.record_write(recipient, sender, content)
    - 每次 mailbox 消费：tracker.record_consume(recipient, messages)
    - 跑完后从 tracker 读 delegation_chain / total_messages / successful_messages
    """

    # 初始化空追踪器
    def __init__(self) -> None:
        self.delegation_chain: list[DelegationStep] = []
        self.total_messages: int = 0
        self.successful_messages: int = 0
        # 内部观测：写与消费的对应关系
        self._writes: list[tuple[str, str, str]] = []  # (recipient, sender, content)
        self._consumes: list[tuple[str, int]] = []  # (recipient, msg_count)

    # 记录一次 mailbox write；推一条 DelegationStep 到委派链
    def record_write(
        self,
        recipient: str,
        sender: str,
        content: str,
        sub_task: str = "",
    ) -> DelegationStep:
        """记录一次 mailbox write；返回构造的 DelegationStep。"""
        step = DelegationStep(
            from_member=sender,
            to_member=recipient,
            sub_task=sub_task or content[:40],
            ts=_now_iso(),
        )
        self._writes.append((recipient, sender, content))
        self.delegation_chain.append(step)
        # 委派链的"消息"也算 mailbox 消息（write 与 consume 一一对应）
        return step

    # 记录一次 mailbox consume；累加 successful_messages
    def record_consume(
        self,
        recipient: str,
        messages: list[dict[str, str]],
    ) -> int:
        """记录一次 mailbox consume；返回消费的条数。"""
        count = len(messages)
        self._consumes.append((recipient, count))
        self.total_messages += count
        self.successful_messages += count
        return count

    # 把 tracker 状态同步到 TeamEvalResult（含 events 写入）
    def attach_to(
        self,
        result: TeamEvalResult,
        *,
        emit_events: bool = True,
    ) -> None:
        """把 tracker 状态同步到 TeamEvalResult（委派链 + 统计 + 事件）。"""
        result.delegation_chain = list(self.delegation_chain)
        result.total_messages = self.total_messages
        result.successful_messages = self.successful_messages
        if not emit_events:
            return
        # 把每次 write 落成 handoff 事件（便于前端时间轴展示）
        for step in self.delegation_chain:
            result.events.append(
                CaseEvent(
                    type="team.handoff",
                    ts=step.ts,
                    data={
                        "from": step.from_member,
                        "to": step.to_member,
                        "sub_task": step.sub_task,
                    },
                )
            )

    # 统计每个收件人收到的消息数（用于 debug / 集成期）
    def messages_by_recipient(self) -> dict[str, int]:
        """统计每个收件人收到的消息数。"""
        out: dict[str, int] = {}
        for r, _, _ in self._writes:
            out[r] = out.get(r, 0) + 1
        return out
