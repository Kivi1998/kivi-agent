"""T11 多 Agent 协作评测（agent: package-eval-team-v52）。

# __init__.py（agent: package-eval-team-v52）
Wave 5.2 T11：team case 数据集 + team runner + mailbox tracker + 6 团队指标。

公开 API：
- TeamCase / TeamDataset：JSONL 数据集（line 1 = 1 team case）
- TeamEvalResult / MemberOutcome / DelegationStep：单 team 运行结果
- TeamRunner：并发跑 team 数据集（asyncio.Semaphore）
- MailboxTracker：监听 mailbox 写消费 → 委派链 + handoff 计数
- team_executor：mock 版 case 执行器（用 LLM 跑一步 + 按 case 委派）

**与 v1 契约关系**：
- 不修改 v1 §1 业务 Tool 名
- 不修改 v1 §5.2.1 现有 6 事件
- 委派 / handoff / team 状态通过 `EvalResult.events` 的扩展 type 记录
  （team.created / team.member_dispatched / team.handoff / team.finished /
   team.unassigned），不新增 v1 事件类
"""
from kivi_agent.eval.team.mailbox_tracker import MailboxTracker
from kivi_agent.eval.team.models import (
    DelegationStep,
    MemberOutcome,
    MemberSpec,
    SubTaskSpec,
    TeamCase,
    TeamDataset,
    TeamEvalResult,
)
from kivi_agent.eval.team.team_executor import execute_case
from kivi_agent.eval.team.team_runner import TeamRunner

__all__ = [
    "DelegationStep",
    "MailboxTracker",
    "MemberOutcome",
    "MemberSpec",
    "SubTaskSpec",
    "TeamCase",
    "TeamDataset",
    "TeamEvalResult",
    "TeamRunner",
    "execute_case",
]
