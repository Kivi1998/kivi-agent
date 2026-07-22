from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TeammateInfo:
    name: str
    role: str
    run_id: str
    status: str = "pending"  # "pending" | "running" | "success" | "failed"


@dataclass
class AgentTeam:
    id: str
    goal: str
    members: list[TeammateInfo] = field(default_factory=list)

    # 按名字查找团队成员；不存在返回 None
    def find_member(self, name: str) -> TeammateInfo | None:
        for m in self.members:
            if m.name == name:
                return m
        return None
