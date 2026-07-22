"""Skills 2.0 公共 API。

旧 API（Wave 1 兼容）：Skill / SkillLoader
新 API（Skills 2.0）：SkillDefinition / SkillRegistry / SkillManager /
                    SkillContentReader / SkillScriptExecutor
"""
from kivi_agent.core.skills.content_reader import (
    ContentTooLargeError,
    DEFAULT_MAX_BYTES,
    SkillContentReader,
)
from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.loader import Skill, SkillLoader
from kivi_agent.core.skills.manager import SkillManager
from kivi_agent.core.skills.registry import SkillRegistry
from kivi_agent.core.skills.script_executor import (
    SkillScriptError,
    SkillTimeoutError,
    execute_skill_script,
)

__all__ = [
    # 旧 API（兼容 SessionManager / TUI / 现有调用方）
    "Skill",
    "SkillLoader",
    # Skills 2.0 新 API
    "SkillDefinition",
    "SkillRegistry",
    "SkillManager",
    "SkillContentReader",
    "ContentTooLargeError",
    "DEFAULT_MAX_BYTES",
    "execute_skill_script",
    "SkillScriptError",
    "SkillTimeoutError",
]
