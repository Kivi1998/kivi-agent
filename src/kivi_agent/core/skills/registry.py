"""Skills 2.0 SkillRegistry：内存索引 + 用户级/项目级启停。

契约冻结 v1 §5.2.2 推迟项 + 整合方案 §7.2 + B 分析报告 §"用户级 / 项目级 Skill 启停"。

设计要点：
- 同名覆盖按 source 优先级：project > user > builtin
- 三层启停状态：项目级（最高）> 用户级 > 默认（启用）
- 启停存储在内存 dict；Wave 2 可加 file/DB 后端（与 aigroup skill_settings_store 行为一致）
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Literal

from kivi_agent.core.skills.definition import SkillDefinition

logger = logging.getLogger(__name__)


# 同名覆盖优先级（数值越大优先级越高）
_SOURCE_PRIORITY: dict[str, int] = {"builtin": 0, "user": 1, "project": 2}
Scope = Literal["user", "project"]


class SkillRegistry:
    """Skill 元数据内存索引 + 启停控制。"""

    def __init__(self) -> None:
        # name → SkillDefinition；同名按 source 优先级替换并 warn
        self._skills: dict[str, SkillDefinition] = {}
        # user_id → {name: True}；True = disabled（仅记录 disabled 状态）
        self._user_disabled: dict[str, dict[str, bool]] = {}
        # scope=project 时存这里；同样 True = disabled
        self._project_disabled: set[str] = set()
        # scope=project 时存 enabled（强制启用）
        self._project_enabled: set[str] = set()

    # ──────────── 注册 / 读取 ────────────

    # 注册一个 SkillDefinition；同名时按 source 优先级替换并 warn
    def register(self, skill: SkillDefinition) -> None:
        existing = self._skills.get(skill.name)
        if existing is not None:
            if _SOURCE_PRIORITY.get(skill.source, 0) <= _SOURCE_PRIORITY.get(existing.source, 0):
                logger.warning(
                    "skill '%s' from source '%s' ignored, kept existing source '%s'",
                    skill.name,
                    skill.source,
                    existing.source,
                )
                return
            logger.warning(
                "skill '%s' overridden by source '%s' (was '%s')",
                skill.name,
                skill.source,
                existing.source,
            )
        self._skills[skill.name] = skill

    # 按 name 查；不存在返回 None
    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    # 全部已注册 skill（注册顺序）
    def list_all(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    # 按 category 过滤；空列表表示该分类无注册
    def list_by_category(self, category: str) -> list[SkillDefinition]:
        return [s for s in self._skills.values() if s.category == category]

    # ──────────── 启停 ────────────

    # 启用 skill。scope=project 强制启用；scope=user 仅对指定 user 启用
    def enable(self, name: str, user: str | None = None, *, scope: Scope = "user") -> None:
        if scope == "project":
            self._project_enabled.add(name)
            self._project_disabled.discard(name)
            return
        assert user is not None, "user scope requires user"
        bucket = self._user_disabled.setdefault(user, {})
        bucket.pop(name, None)

    # 关闭 skill。scope=project 强制关闭；scope=user 仅对指定 user 关闭
    def disable(self, name: str, user: str | None = None, *, scope: Scope = "user") -> None:
        if scope == "project":
            self._project_disabled.add(name)
            self._project_enabled.discard(name)
            return
        assert user is not None, "user scope requires user"
        bucket = self._user_disabled.setdefault(user, {})
        bucket[name] = True

    # 查询启停状态。三层：未注册 → True（不在仓库内的 skill 不视为"已禁用"）；
    # 项目 disabled → False；项目 enabled → True；否则查 user disabled；都没有 → True
    def is_enabled(self, name: str, user: str) -> bool:
        if name not in self._skills:
            return True
        if name in self._project_disabled:
            return False
        if name in self._project_enabled:
            return True
        bucket = self._user_disabled.get(user, {})
        return name not in bucket

    # ──────────── 工具方法 ────────────

    def clear(self) -> None:
        """清空注册 + 启停状态（主要用于测试）。"""
        self._skills.clear()
        self._user_disabled.clear()
        self._project_disabled.clear()
        self._project_enabled.clear()

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._skills

    def __iter__(self) -> Iterator[SkillDefinition]:
        return iter(self._skills.values())
