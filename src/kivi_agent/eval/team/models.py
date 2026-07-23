"""T11 多 Agent 协作评测数据类（agent: package-eval-team-v52）。

# models.py（agent: package-eval-team-v52）
- TeamCase / TeamDataset：JSONL 数据集（每行一个 team case）
- TeamEvalResult / MemberOutcome / DelegationStep：单 team 运行结果
- 路径遍历保护：路径段含 ".." 直接拒绝
- v1 契约内不新增事件；team 事件以 `type` 字符串记录在 `events` 字段
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from kivi_agent.eval.result import CaseEvent

# v1 不冻结 team 角色；用 Literal 给出常用集 + 允许自定义（"" 表示未指定）
TeamRole = Literal["planner", "executor", "reviewer", "coordinator", "researcher", "writer", ""]

TeamDifficulty = Literal["easy", "medium", "hard"]


# 当前 UTC 时间的 ISO 8601 字符串（用于 ts 字段默认）
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# 团队成员规格（agent: package-eval-team-v52）
class MemberSpec(BaseModel):
    """团队成员规格：name / role / prompt。

    设计：role 留空字符串时表示"未指定角色"（executor 仍可工作）。
    """

    name: str
    role: str = ""
    prompt: str = ""


# 子任务规格：assignee 引用 member_specs.name（agent: package-eval-team-v52）
class SubTaskSpec(BaseModel):
    """子任务规格：assignee（成员名）+ topic。"""

    assignee: str
    topic: str


# 单个 team case（agent: package-eval-team-v52）
class TeamCase(BaseModel):
    """单个 team 评测 case。

    字段约定（与 Wave 5.2 plan §三 WT-H1 JSONL 字段一致）：
    - member_specs：成员规格列表（name / role / prompt）
    - sub_tasks：计划派发的子任务列表（assignee + topic）
    - expected_assignments：每个成员期望接收的子任务数（用于 delegation_accuracy）
    - expected_total_messages：期望的总 mailbox 消息数（用于 handoff_quality）
    - max_steps_per_member：单成员最大步数（限制 LLM 循环）
    - difficulty：easy / medium / hard
    """

    id: str
    goal: str
    member_specs: list[MemberSpec] = Field(default_factory=list)
    sub_tasks: list[SubTaskSpec] = Field(default_factory=list)
    expected_assignments: dict[str, int] = Field(default_factory=dict)
    expected_total_messages: int = 0
    max_steps_per_member: int = 10
    difficulty: TeamDifficulty = "medium"
    notes: str | None = None


# team 数据集（agent: package-eval-team-v52）
class TeamDataset(BaseModel):
    """team 数据集（JSONL 一行一 case）。"""

    name: str
    cases: list[TeamCase]

    # 从 JSONL 文件加载数据集
    @classmethod
    def load(cls, path: Path) -> TeamDataset:
        """从 JSONL 文件加载（每行一个 TeamCase）。"""
        # 路径遍历保护：拒绝任何含 ".." 的路径
        if ".." in path.parts:
            raise ValueError(f"invalid team dataset path: {path}")
        cases: list[TeamCase] = []
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    cases.append(TeamCase(**data))
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"line {line_no} invalid: {e}") from e
        return cls(name=path.stem, cases=cases)

    # 按 tag-free 难度过滤（team case 无 tags 字段；按 difficulty 过滤）
    def filter_by_difficulty(self, difficulty: TeamDifficulty) -> TeamDataset:
        """按 difficulty 过滤；返回新 TeamDataset（name 标记难度）。"""
        return TeamDataset(
            name=f"{self.name}_diff_{difficulty}",
            cases=[c for c in self.cases if c.difficulty == difficulty],
        )


# 委派步骤：单次 mailbox 写入（agent: package-eval-team-v52）
class DelegationStep(BaseModel):
    """一次委派步骤记录（mailbox write 触发）。

    字段：from_member / to_member / sub_task / ts。
    """

    from_member: str
    to_member: str
    sub_task: str
    ts: str = Field(default_factory=_now_iso)


# 单成员执行结果（agent: package-eval-team-v52）
class MemberOutcome(BaseModel):
    """单成员执行结果。

    字段：name / role / run_id / success / tool_calls_count / steps / finished_at。
    """

    name: str
    role: str = ""
    run_id: str
    success: bool = False
    tool_calls_count: int = 0
    steps: int = 0
    finished_at: str | None = None


# 单 team 评测结果（agent: package-eval-team-v52）
class TeamEvalResult(BaseModel):
    """单 team 评测结果。

    设计要点（与 Wave 5.2 plan §三 WT-H1 一致）：
    - team_id：单 team 唯一 ID
    - member_outcomes：每个成员的执行结果
    - delegation_chain：team 全部委派步骤（按时间顺序）
    - events：扩展 type 的事件流（team.created / team.member_dispatched /
      team.handoff / team.finished / team.unassigned），不新增 v1 事件类
    - planned_assignments / actual_assignments：用于 delegation_accuracy 指标
    - total_messages / successful_messages：用于 handoff_quality 指标
    - role_changes：用于 role_consistency 指标
    """

    team_id: str
    goal: str
    started_at: str = Field(default_factory=_now_iso)
    finished_at: str | None = None
    success: bool = False
    error: str | None = None
    # 成员与委派
    member_outcomes: list[MemberOutcome] = Field(default_factory=list)
    delegation_chain: list[DelegationStep] = Field(default_factory=list)
    # 事件流（扩展 type 字符串，不新增 v1 事件类）
    events: list[CaseEvent] = Field(default_factory=list)
    # 汇总统计（供 6 指标读取）
    total_messages: int = 0
    successful_messages: int = 0
    role_changes: int = 0
    # 委派准确性：计划 vs 实际
    planned_assignments: dict[str, int] = Field(default_factory=dict)
    actual_assignments: dict[str, int] = Field(default_factory=dict)
