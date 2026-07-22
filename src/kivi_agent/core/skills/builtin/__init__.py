"""内建 skill 集合：6 个（4 旧 + 2 新）。

B 阶段 Skills 2.0：把 builtin/*.md 统一注册进 SkillRegistry。
旧 skill（init / orchestrate / review / summarize）保持向后兼容 +
加 Skills 2.0 字段（category / 双模式 / runtime_context_keys）。
新 skill（search_kb / web_lookup）演示 v1 锁定的 6 个 Tool 名引用。
"""
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.registry import SkillRegistry


# 6 个内建 skill 名（按注册顺序展示）
BUILTIN_SKILLS_V1: tuple[str, ...] = (
    "init",
    "orchestrate",
    "review",
    "summarize",
    "search_kb",
    "web_lookup",
)

# builtin 目录（绝对路径）
_BUILTIN_DIR = Path(__file__).parent


# 列出 builtin/ 下所有 SKILL.md / .md 文件（绝对路径）
def iter_builtin_files() -> list[Path]:
    if not _BUILTIN_DIR.exists():
        return []
    out: list[Path] = []
    for f in sorted(_BUILTIN_DIR.glob("*.md")):
        out.append(f)
    return out


# 解析单个内建 skill 为 SkillDefinition
def load_builtin_definition(name: str) -> SkillDefinition:
    path = _BUILTIN_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"builtin skill not found: {name}")
    return SkillDefinition.from_file(path, source="builtin")


# 构建包含全部 6 个内建 skill 的 SkillRegistry
def build_builtin_registry() -> SkillRegistry:
    reg = SkillRegistry()
    for name in BUILTIN_SKILLS_V1:
        reg.register(load_builtin_definition(name))
    return reg
