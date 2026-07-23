"""长期记忆字段类型字面量（Wave 6.1 J2 增强）。"""

from __future__ import annotations

from typing import Literal

# 记忆类型：user 个人偏好 / feedback 反馈 / project 项目事实 /
# reference 参考资料 / task 任务上下文。
MemoryType = Literal["user", "feedback", "project", "reference", "task"]

# 记忆状态：active 生效中 / pending 待确认 / archived 已归档 / expired 已过期。
MemoryStatus = Literal["active", "pending", "archived", "expired"]

# 重要度 0.0-1.0，由 LLM 抽取时评分或由用户/管理员手动调整。
MemoryImportance = float
