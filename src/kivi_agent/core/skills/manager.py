"""SkillManager：对外统一入口（整合 SkillRegistry）。

设计要点：
- 内部用 SkillRegistry 存 SkillDefinition
- 对外暴露旧 API（resolve / render_prompt / list_all_skills）以兼容 SessionManager / TUI
- 对外暴露新 API（get / list_by_category / register / enable / disable / is_enabled）
- 默认构造时自动加载全部内建 skill
"""
from __future__ import annotations

import logging

from kivi_agent.core.skills.builtin import BUILTIN_SKILLS_V1, load_builtin_definition
from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.loader import Skill
from kivi_agent.core.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


# 把 SkillDefinition 转回旧 Skill 形状（SessionManager / TUI 调用方依赖）
def _to_legacy_skill(sd: SkillDefinition) -> Skill:
    return Skill(
        name=sd.name,
        description=sd.description,
        system_prompt_template=sd.system_prompt_template,
        allowed_tools=list(sd.allowed_tools),
    )


class SkillManager:
    """Skill 对外统一入口：内部用 SkillRegistry 存 SkillDefinition。"""

    def __init__(self, *, registry: SkillRegistry | None = None) -> None:
        self._registry = registry if registry is not None else SkillRegistry()
        if registry is None:
            self._load_builtins()

    # 加载全部内建 skill；个别失败不阻断其他（log warn 后继续）
    def _load_builtins(self) -> None:
        for name in BUILTIN_SKILLS_V1:
            try:
                self._registry.register(load_builtin_definition(name))
            except FileNotFoundError:
                logger.warning("builtin skill file not found, skipped: %s", name)
            except Exception as e:  # noqa: BLE001  # 解析失败不阻断 manager
                logger.warning("failed to load builtin skill '%s': %s", name, e)

    # ──────────── 新 API（Skills 2.0） ────────────

    @property
    def registry(self) -> SkillRegistry:
        """暴露内部 registry，供其他 Agent 注入 / 查询。"""
        return self._registry

    # 注册一个 SkillDefinition 到 registry
    def register(self, skill: SkillDefinition) -> None:
        self._registry.register(skill)

    # 按 name 查 SkillDefinition；不存在返回 None
    def get(self, name: str) -> SkillDefinition | None:
        return self._registry.get(name)

    # 按 category 过滤
    def list_by_category(self, category: str) -> list[SkillDefinition]:
        return self._registry.list_by_category(category)

    # 全部 SkillDefinition
    def list_all(self) -> list[SkillDefinition]:
        return self._registry.list_all()

    # 启停控制（透传 registry）
    def enable(self, name: str, user: str | None = None, *, scope: str = "user") -> None:
        self._registry.enable(name, user=user, scope=scope)  # type: ignore[arg-type]

    def disable(self, name: str, user: str | None = None, *, scope: str = "user") -> None:
        self._registry.disable(name, user=user, scope=scope)  # type: ignore[arg-type]

    def is_enabled(self, name: str, user: str) -> bool:
        return self._registry.is_enabled(name, user)

    # ──────────── 旧 API（兼容 SessionManager / TUI 调用方） ────────────

    # 按 name 查旧 Skill 形状（供 /skill 命令路径）
    def resolve(self, name: str) -> Skill | None:
        sd = self._registry.get(name)
        if sd is None:
            return None
        return _to_legacy_skill(sd)

    # 替换 $ARGUMENTS 占位符（与旧 SkillLoader.render_prompt 行为一致）
    def render_prompt(self, skill: Skill, arguments: str) -> str:
        return skill.system_prompt_template.replace("$ARGUMENTS", arguments)

    # 全部 Skill（旧形状列表，供 TUI 弹窗）
    def list_all_skills(self) -> list[Skill]:
        return [_to_legacy_skill(sd) for sd in self._registry.list_all()]

    # ──────────── 容器协议 ────────────

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: object) -> bool:
        return name in self._registry
