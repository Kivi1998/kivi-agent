"""SkillManager 整合 SkillRegistry 测试。

SkillManager 是对外统一入口：
- 内部用 SkillRegistry 存 SkillDefinition
- 对外暴露 resolve() / render_prompt() / list_all_skills() 等旧 API
  （保持 SessionManager / TUI 调用方零修改）
- 额外暴露 Skills 2.0 新 API（list_by_category / enable / disable）
"""
from __future__ import annotations

from kivi_agent.core.skills.builtin import BUILTIN_SKILLS_V1
from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.loader import Skill
from kivi_agent.core.skills.manager import SkillManager
from kivi_agent.core.skills.registry import SkillRegistry

# ─────────────────────────── 构造 ───────────────────────────


# 功能：SkillManager 默认构造带内建 6 个 skill
# 设计：构造 manager，断言 6 个 skill 都在 registry
def test_default_manager_has_builtin_skills() -> None:
    mgr = SkillManager()
    assert len(mgr) == len(BUILTIN_SKILLS_V1)
    for name in BUILTIN_SKILLS_V1:
        assert mgr.get(name) is not None


# 功能：SkillManager 接受外部 registry 注入
# 设计：传入空 registry + 2 个 skill，断言只有 2 个
def test_manager_accepts_custom_registry() -> None:
    reg = SkillRegistry()
    reg.register(SkillDefinition(name="custom1", description="c1"))
    reg.register(SkillDefinition(name="custom2", description="c2"))
    mgr = SkillManager(registry=reg)
    assert len(mgr) == 2
    assert mgr.get("custom1") is not None


# ─────────────────────────── 旧 API 兼容 ───────────────────────────


# 功能：resolve(name) 返回旧 Skill 形状（SessionManager 依赖）
# 设计：resolve "init"，断言返回 Skill（含 name/description/allowed_tools/system_prompt_template）
def test_resolve_returns_legacy_skill_shape() -> None:
    mgr = SkillManager()
    skill = mgr.resolve("init")
    assert isinstance(skill, Skill)
    assert skill.name == "init"
    assert skill.description != ""
    assert skill.system_prompt_template != ""
    assert len(skill.allowed_tools) > 0


# 功能：resolve 不存在时返回 None（不抛异常）
# 设计：resolve("nonexistent")，断言 None
def test_resolve_unknown_returns_none() -> None:
    mgr = SkillManager()
    assert mgr.resolve("nope_xyz") is None


# 功能：render_prompt 替换 $ARGUMENTS 占位符
# 设计：拿 review skill，render_prompt("foo.py")，断言 "$ARGUMENTS" 不在结果
def test_render_prompt_substitutes_arguments() -> None:
    mgr = SkillManager()
    skill = mgr.resolve("review")
    assert skill is not None
    rendered = mgr.render_prompt(skill, "src/foo.py")
    assert "$ARGUMENTS" not in rendered
    assert "src/foo.py" in rendered


# 功能：list_all_skills 返回旧 Skill 形状列表（TUI 依赖）
# 设计：list_all_skills()，断言长度 = 6 且每项是 Skill
def test_list_all_skills_returns_legacy_shape() -> None:
    mgr = SkillManager()
    skills = mgr.list_all_skills()
    assert len(skills) == len(BUILTIN_SKILLS_V1)
    for s in skills:
        assert isinstance(s, Skill)
        assert s.name != ""
        assert s.description != ""


# ─────────────────────────── 新 API ───────────────────────────


# 功能：get(name) 返回 SkillDefinition（Skills 2.0）
# 设计：get "init"，断言 SkillDefinition + category
def test_get_returns_skill_definition() -> None:
    mgr = SkillManager()
    skill = mgr.get("init")
    assert isinstance(skill, SkillDefinition)
    assert skill.category == "general"


# 功能：list_by_category 分类过滤
# 设计：list_by_category("rag") 应只有 search_kb
def test_list_by_category_works() -> None:
    mgr = SkillManager()
    rag_skills = mgr.list_by_category("rag")
    assert {s.name for s in rag_skills} == {"search_kb"}


# 功能：enable / disable / is_enabled 透传到 registry
# 设计：disable "init" for user "alice" → is_enabled False
def test_enable_disable_routes_to_registry() -> None:
    mgr = SkillManager()
    mgr.disable("init", user="alice")
    assert mgr.is_enabled("init", user="alice") is False
    mgr.enable("init", user="alice")
    assert mgr.is_enabled("init", user="alice") is True


# 功能：registry 属性暴露（其他 Agent 可注入）
# 设计：mgr.registry 应是 SkillRegistry 实例
def test_registry_property_exposed() -> None:
    mgr = SkillManager()
    assert isinstance(mgr.registry, SkillRegistry)


# 功能：register 添加外部 skill（不影响内建）
# 设计：register 一个 custom skill，断言 get 能找到
def test_register_adds_skill() -> None:
    mgr = SkillManager()
    mgr.register(SkillDefinition(name="custom", description="my custom"))
    assert mgr.get("custom") is not None
    # 内建 skill 仍在
    assert mgr.get("init") is not None


# ─────────────────────────── 内建解析失败兜底 ───────────────────────────


# 功能：构造时不抛异常（即使个别 skill 解析失败）
# 设计：default 构造，断言 manager 存在
def test_construction_does_not_raise() -> None:
    mgr = SkillManager()
    assert mgr is not None
