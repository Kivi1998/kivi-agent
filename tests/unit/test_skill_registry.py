"""Skills 2.0 SkillRegistry 生命周期管理测试。

契约冻结 v1 §5.2.2 推迟项 + B 分析报告：
- register / get / list_by_category / list_all
- enable / disable / is_enabled（用户级 + 项目级）
- 同名覆盖策略：project > user > builtin
"""
from __future__ import annotations

from kivi_agent.core.skills.definition import SkillDefinition
from kivi_agent.core.skills.registry import SkillRegistry


def _make_skill(name: str, category: str = "general", source: str = "builtin") -> SkillDefinition:
    """构造一个测试用 SkillDefinition 实例。"""
    return SkillDefinition(name=name, description=f"desc-{name}", category=category, source=source)


# ─────────────────────────── register / get / list ───────────────────────────


# 功能：register 后可通过 get 查到
# 设计：注册 1 个 skill，get 找到，断言字段一致
def test_register_then_get() -> None:
    reg = SkillRegistry()
    skill = _make_skill("init", category="general")
    reg.register(skill)
    got = reg.get("init")
    assert got is skill


# 功能：get 不存在的名称返回 None（不抛异常）
# 设计：空 registry 上 get，断言 None
def test_get_unknown_returns_none() -> None:
    reg = SkillRegistry()
    assert reg.get("nope") is None


# 功能：list_all 返回所有已注册 skill（顺序：注册顺序）
# 设计：注册 3 个，断言 list_all 长度 = 3 且包含
def test_list_all_returns_all() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("a"))
    reg.register(_make_skill("b"))
    reg.register(_make_skill("c"))
    all_skills = reg.list_all()
    names = [s.name for s in all_skills]
    assert names == ["a", "b", "c"]


# 功能：list_by_category 仅返回指定分类
# 设计：注册 2 个 rag + 1 个 web_search，list_by_category("rag") 只返回 2 个
def test_list_by_category_filters() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("r1", category="rag"))
    reg.register(_make_skill("r2", category="rag"))
    reg.register(_make_skill("w1", category="web_search"))
    rag_skills = reg.list_by_category("rag")
    assert {s.name for s in rag_skills} == {"r1", "r2"}


# 功能：list_by_category 对空分类返回空列表
# 设计：注册 1 个 general，list_by_category("database") 返回空
def test_list_by_category_empty() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("a", category="general"))
    assert reg.list_by_category("database") == []


# ─────────────────────────── 同名覆盖（优先级） ───────────────────────────


# 功能：project 覆盖 builtin（同名时按 source 优先级）
# 设计：先注册 builtin 同名，再注册 project，应只剩 project（log warn）
def test_project_overrides_builtin() -> None:
    reg = SkillRegistry()
    builtin = _make_skill("init", category="general", source="builtin")
    project = _make_skill("init", category="rag", source="project")
    reg.register(builtin)
    reg.register(project)
    got = reg.get("init")
    assert got is project
    assert got.category == "rag"


# 功能：user 覆盖 builtin
# 设计：先 builtin 再 user，应只剩 user
def test_user_overrides_builtin() -> None:
    reg = SkillRegistry()
    builtin = _make_skill("init", source="builtin")
    user = _make_skill("init", source="user")
    reg.register(builtin)
    reg.register(user)
    assert reg.get("init") is user


# ─────────────────────────── 启停（用户级） ───────────────────────────


# 功能：默认所有 skill 启用
# 设计：注册后立即查 is_enabled，断言 True
def test_default_enabled() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    assert reg.is_enabled("init", user="alice") is True


# 功能：disable 后 is_enabled 返回 False
# 设计：注册 → disable("init", "alice") → 查 is_enabled
def test_disable_then_is_enabled_false() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.disable("init", user="alice")
    assert reg.is_enabled("init", user="alice") is False


# 功能：enable 可恢复被 disable 的 skill
# 设计：disable → enable → 查 is_enabled 应为 True
def test_enable_after_disable() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.disable("init", user="alice")
    reg.enable("init", user="alice")
    assert reg.is_enabled("init", user="alice") is True


# 功能：enable 未被 disable 的 skill（幂等）
# 设计：直接 enable，断言不抛异常且仍 enabled
def test_enable_idempotent() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.enable("init", user="alice")
    assert reg.is_enabled("init", user="alice") is True


# 功能：用户级启停隔离：alice 关闭不影响 bob
# 设计：注册 → alice disable → bob is_enabled 仍 True
def test_user_scoping_isolation() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.disable("init", user="alice")
    assert reg.is_enabled("init", user="alice") is False
    assert reg.is_enabled("init", user="bob") is True


# 功能：禁用不存在的 skill 不抛异常（幂等 disable）
# 设计：直接 disable 一个未注册的名字，断言 is_enabled 返回 True（默认）
def test_disable_unknown_skill_idempotent() -> None:
    reg = SkillRegistry()
    reg.disable("ghost", user="alice")
    assert reg.is_enabled("ghost", user="alice") is True


# ─────────────────────────── 统计 / 工具方法 ───────────────────────────


# 功能：__len__ 反映已注册 skill 数
# 设计：注册 0/1/3 个，断言 len 正确
def test_len() -> None:
    reg = SkillRegistry()
    assert len(reg) == 0
    reg.register(_make_skill("a"))
    assert len(reg) == 1
    reg.register(_make_skill("b"))
    reg.register(_make_skill("c"))
    assert len(reg) == 3


# 功能：__contains__ 反映是否注册
# 设计：注册 a，断言 "a" in reg 为 True；"b" 为 False
def test_contains() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("a"))
    assert "a" in reg
    assert "b" not in reg


# 功能：clear 清空所有注册 + 启停状态
# 设计：注册 2 个 + 1 个 disable，clear 后 len=0 且状态全默认
def test_clear_resets_state() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("a"))
    reg.register(_make_skill("b"))
    reg.disable("a", user="alice")
    reg.clear()
    assert len(reg) == 0
    assert reg.get("a") is None
    # 状态也清空：再 register 时 a 默认 enabled
    reg.register(_make_skill("a"))
    assert reg.is_enabled("a", user="alice") is True


# ─────────────────────────── 项目级启停（v1 推迟到 D 阶段） ───────────────────────────


# 功能：项目级 disable 优先级高于用户级 enable
# 设计：alice 先 enable init，再项目级 disable → is_enabled 应为 False
def test_project_disable_overrides_user_enable() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.enable("init", user="alice")
    reg.disable("init", scope="project")
    assert reg.is_enabled("init", user="alice") is False


# 功能：项目级 enable 强制启用（即便用户曾 disable）
# 设计：alice disable → 项目 enable → 应 enabled
def test_project_enable_overrides_user_disable() -> None:
    reg = SkillRegistry()
    reg.register(_make_skill("init"))
    reg.disable("init", user="alice")
    reg.enable("init", scope="project")
    assert reg.is_enabled("init", user="alice") is True
