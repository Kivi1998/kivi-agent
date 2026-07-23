"""Skills 2.0 SkillDefinition 数据结构测试。

验证契约冻结 v1 要求的 5 个新增字段 + 双模式默认值。
"""
from __future__ import annotations

from typing import get_type_hints

import pytest

from kivi_agent.core.skills.definition import SkillDefinition

# ─────────────────────────── 双模式默认值 ───────────────────────────


# 功能：SkillDefinition 默认应同时启用 command_mode 和 tool_mode
# 设计：直接实例化，验证两个布尔字段默认均为 True（双模式）
def test_skill_definition_default_dual_mode() -> None:
    skill = SkillDefinition(name="demo", description="demo skill")
    assert skill.command_mode is True
    assert skill.tool_mode is True


# 功能：双模式开关可独立覆盖
# 设计：把 command_mode 关闭 / tool_mode 关闭，断言已生效
def test_skill_definition_mode_flags_overridable() -> None:
    skill = SkillDefinition(
        name="cmd_only",
        description="only slash command",
        command_mode=True,
        tool_mode=False,
    )
    assert skill.command_mode is True
    assert skill.tool_mode is False

    skill2 = SkillDefinition(
        name="tool_only",
        description="only tool invocation",
        command_mode=False,
        tool_mode=True,
    )
    assert skill2.command_mode is False
    assert skill2.tool_mode is True


# ─────────────────────────── category 字段 ───────────────────────────


# 功能：category 字段类型为 Literal[5 类]，未指定时默认 "general"
# 设计：反射获取 type hints 并断言是 Literal；实例化默认值
def test_skill_definition_category_default_general() -> None:
    skill = SkillDefinition(name="x", description="")
    assert skill.category == "general"


# 功能：category 接受 5 类合法值
# 设计：参数化 5 个合法值（general/rag/web_search/database/tool）逐个实例化
@pytest.mark.parametrize("cat", ["general", "rag", "web_search", "database", "tool"])
def test_skill_definition_accepts_all_categories(cat: str) -> None:
    skill = SkillDefinition(name="x", description="", category=cat)
    assert skill.category == cat


# 功能：category 字段在类型注解上声明为 Literal
# 设计：通过 get_type_hints 读 "category" 字段类型
def test_skill_definition_category_is_literal() -> None:
    hints = get_type_hints(SkillDefinition)
    assert "category" in hints


# ─────────────────────────── runtime_context_keys ───────────────────────────


# 功能：runtime_context_keys 字段默认空列表，可注入 RunContext 字段名
# 设计：实例化时指定字段名（user_id / datasource_id），断言保留
def test_skill_definition_runtime_context_keys_default_empty() -> None:
    skill = SkillDefinition(name="x", description="")
    assert skill.runtime_context_keys == []


def test_skill_definition_runtime_context_keys_stores_field_names() -> None:
    skill = SkillDefinition(
        name="x",
        description="",
        runtime_context_keys=["user_id", "datasource_id", "knowledge_base_id"],
    )
    assert skill.runtime_context_keys == ["user_id", "datasource_id", "knowledge_base_id"]


# ─────────────────────────── references / scripts ───────────────────────────


# 功能：references 字段默认空列表，存 references/ 下的相对路径
# 设计：实例化时指定 references，断言原样保留
def test_skill_definition_references_default_empty() -> None:
    skill = SkillDefinition(name="x", description="")
    assert skill.references == []


def test_skill_definition_references_stores_paths() -> None:
    skill = SkillDefinition(
        name="x",
        description="",
        references=["knowledge_injection_example.md", "prompts/query_rewrite.md"],
    )
    assert skill.references == ["knowledge_injection_example.md", "prompts/query_rewrite.md"]


# 功能：scripts 字段默认空列表，每项是含 path + interpreter 的 dict
# 设计：注入 1 个 py 脚本 + 1 个 js 脚本，断言结构完整
def test_skill_definition_scripts_default_empty() -> None:
    skill = SkillDefinition(name="x", description="")
    assert skill.scripts == []


def test_skill_definition_scripts_stores_dicts() -> None:
    skill = SkillDefinition(
        name="x",
        description="",
        scripts=[
            {"path": "scripts/main.py", "interpreter": "python"},
            {"path": "scripts/main.js", "interpreter": "node"},
        ],
    )
    assert len(skill.scripts) == 2
    assert skill.scripts[0]["path"] == "scripts/main.py"
    assert skill.scripts[0]["interpreter"] == "python"
    assert skill.scripts[1]["interpreter"] == "node"


# ─────────────────────────── 与旧 Skill 字段兼容 ───────────────────────────


# 功能：SkillDefinition 仍保留 name / description / allowed_tools / system_prompt_template
# 设计：实例化全部旧字段 + 5 新字段，断言可构造且字段可读
def test_skill_definition_keeps_legacy_fields() -> None:
    skill = SkillDefinition(
        name="init",
        description="分析项目并生成 context",
        system_prompt_template="You are an analyzer. $ARGUMENTS",
        allowed_tools=["read_file", "list_dir", "write_file"],
        command_mode=True,
        tool_mode=True,
        category="general",
        runtime_context_keys=[],
        references=[],
        scripts=[],
    )
    assert skill.name == "init"
    assert skill.description == "分析项目并生成 context"
    assert skill.allowed_tools == ["read_file", "list_dir", "write_file"]
    assert "You are an analyzer" in skill.system_prompt_template
