"""Skills 2.0 6 个内建 Skill 迁移测试。

验证 4 个旧 skill（init/orchestrate/review/summarize）迁移后仍可用 +
2 个新 skill（search_kb/web_lookup）以 Skills 2.0 元数据注册。

新 skill 走 SkillDefinition.from_file() 解析（支持新字段）；
旧 skill 兼容旧 SkillLoader（验证 frontmatter 仍可被解析、可用）。
"""
from __future__ import annotations

import pytest

from kivi_agent.core.skills.builtin import (
    BUILTIN_SKILLS_V1,
    build_builtin_registry,
    iter_builtin_files,
    load_builtin_definition,
)
from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.loader import SkillLoader

# ─────────────────────────── 6 个 skill 文件存在 ───────────────────────────


# 功能：6 个内建 skill 全部以 SKILL.md 形式存在于 builtin 目录
# 设计：直接列举文件名 + 断言全部存在
def test_six_builtin_skill_files_exist() -> None:
    expected = {"init", "orchestrate", "review", "summarize", "search_kb", "web_lookup"}
    found = {p.stem for p in iter_builtin_files()}
    assert expected <= found, f"missing: {expected - found}"


# ─────────────────────────── 旧 skill 兼容（SkillLoader 仍可用） ───────────────────────────


# 功能：旧 SkillLoader 仍能找到 4 个旧 skill
# 设计：分别 resolve 4 个名字，断言非 None 且字段完整
@pytest.mark.parametrize("name", ["init", "orchestrate", "review", "summarize"])
def test_old_skill_loader_still_finds_legacy_skills(name: str) -> None:
    loader = SkillLoader()
    skill = loader.resolve(name)
    assert skill is not None, f"legacy skill '{name}' not found by SkillLoader"
    assert skill.name == name
    assert skill.system_prompt_template != ""
    assert len(skill.allowed_tools) > 0


# ─────────────────────────── 新 skill 走 SkillDefinition 解析 ───────────────────────────


# 功能：2 个新 skill 能被 SkillDefinition.from_file() 解析
# 设计：解析 search_kb / web_lookup，断言 category / 双模式 / runtime_context_keys
@pytest.mark.parametrize("name,expected_category", [
    ("search_kb", "rag"),
    ("web_lookup", "web_search"),
])
def test_new_skill_parses_with_skill_definition(
    name: str, expected_category: str
) -> None:
    skill = load_builtin_definition(name)
    assert isinstance(skill, SkillDefinition)
    assert skill.name == name
    assert skill.category == expected_category
    assert skill.command_mode is True
    assert skill.tool_mode is True
    assert skill.system_prompt_template != ""


# 功能：search_kb 声明使用 rag_query 工具（v1 锁定名）
# 设计：解析 search_kb，断言 allowed_tools 含 rag_query
def test_search_kb_uses_frozen_rag_query_tool_name() -> None:
    skill = load_builtin_definition("search_kb")
    assert "rag_query" in skill.allowed_tools


# 功能：web_lookup 声明使用 web_search 工具（v1 锁定名）
# 设计：解析 web_lookup，断言 allowed_tools 含 web_search
def test_web_lookup_uses_frozen_web_search_tool_name() -> None:
    skill = load_builtin_definition("web_lookup")
    assert "web_search" in skill.allowed_tools


# ─────────────────────────── 旧 skill 也支持 SkillDefinition 解析 ───────────────────────────


# 功能：4 个旧 skill 也能以 SkillDefinition 形式加载（默认 category=general）
# 设计：解析 4 个旧 skill，断言 category=general 且双模式
@pytest.mark.parametrize("name", ["init", "orchestrate", "review", "summarize"])
def test_legacy_skill_loads_as_skill_definition_default_general(name: str) -> None:
    skill = load_builtin_definition(name)
    assert skill.category == "general"
    assert skill.command_mode is True
    assert skill.tool_mode is True


# ─────────────────────────── 批量构建 builtin registry ───────────────────────────


# 功能：build_builtin_registry() 把全部 6 个内建 skill 注册到 SkillRegistry
# 设计：构建 registry + 断言 6 个都在 + 各分类计数
def test_build_builtin_registry_has_all_six() -> None:
    reg = build_builtin_registry()
    names = {s.name for s in reg.list_all()}
    expected = {"init", "orchestrate", "review", "summarize", "search_kb", "web_lookup"}
    assert expected <= names


# 功能：build_builtin_registry 正确分类
# 设计：断言 rag=1（search_kb）/ web_search=1（web_lookup）/ general=4（旧 4 个）
def test_build_builtin_registry_category_counts() -> None:
    reg = build_builtin_registry()
    assert len(reg.list_by_category("rag")) == 1
    assert len(reg.list_by_category("web_search")) == 1
    assert len(reg.list_by_category("general")) == 4


# 功能：search_kb 声明 runtime_context_keys 含 knowledge_base_id（v1 §2 字段）
# 设计：解析 search_kb，断言 runtime_context_keys 含 knowledge_base_id
def test_search_kb_runtime_context_keys_match_v1() -> None:
    skill = load_builtin_definition("search_kb")
    assert "knowledge_base_id" in skill.runtime_context_keys


# 功能：web_lookup 声明 runtime_context_keys 含 user_id
# 设计：解析 web_lookup，断言 runtime_context_keys 含 user_id
def test_web_lookup_runtime_context_keys_match_v1() -> None:
    skill = load_builtin_definition("web_lookup")
    assert "user_id" in skill.runtime_context_keys


# 功能：search_kb 声明 references 字段
# 设计：断言 references 是非空 list
def test_search_kb_has_references() -> None:
    skill = load_builtin_definition("search_kb")
    assert isinstance(skill.references, list)
    assert len(skill.references) > 0


# 功能：search_kb 声明 scripts 字段
# 设计：断言 scripts 是非空 list 且每项含 path + interpreter
def test_search_kb_has_scripts() -> None:
    skill = load_builtin_definition("search_kb")
    assert len(skill.scripts) > 0
    assert "path" in skill.scripts[0]
    assert "interpreter" in skill.scripts[0]


# 功能：summarize 旧 frontmatter 的 note_save 工具名仍可见（警告：v1 冻结为 memory_save）
# 设计：仅记录当前状态；不强制替换（C 阶段负责迁移 frontmatter 引用）
def test_summarize_legacy_note_save_tool_visible() -> None:
    skill = load_builtin_definition("summarize")
    # 当前仍为旧名 note_save；C 阶段会改为 memory_save
    assert "note_save" in skill.allowed_tools or "memory_save" in skill.allowed_tools


# 功能：BUILTIN_SKILLS_V1 是 6 个 skill 名的有序 tuple（文档/D 阶段依赖）
# 设计：断言长度=6 + 包含全部预期名
def test_builtin_skills_v1_constant() -> None:
    assert len(BUILTIN_SKILLS_V1) == 6
    assert set(BUILTIN_SKILLS_V1) == {
        "init", "orchestrate", "review", "summarize", "search_kb", "web_lookup",
    }
