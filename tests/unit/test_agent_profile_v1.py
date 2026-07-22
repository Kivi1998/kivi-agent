from __future__ import annotations

import pytest
from pathlib import Path

from kivi_agent.core.agents.loader import AgentProfile, AgentProfileLoader
from kivi_agent.core.permissions.modes import PermissionMode


# 功能：AgentProfile 5 个 v1 新字段都有正确的默认值
# 设计：仅用 name 构造，断言 max_steps=20 / permission_mode=DEFAULT / result_schema=None /
#      concurrency_group="default" / category="other"；这是 v1 §3 表格的默认列
def test_v1_field_defaults() -> None:
    p = AgentProfile(name="x")
    assert p.max_steps == 20
    assert p.permission_mode == PermissionMode.DEFAULT
    assert p.result_schema is None
    assert p.concurrency_group == "default"
    assert p.category == "other"


# 功能：AgentProfile 5 个 v1 新字段能显式赋值
# 设计：构造时全部传非默认值，断言 5 字段完整保留（v1 §3 表格"来源约束"列指向包 B3 + 方案 §6.3）
def test_v1_fields_assignable() -> None:
    p = AgentProfile(
        name="custom",
        max_steps=50,
        permission_mode=PermissionMode.BYPASS,
        result_schema={"type": "object"},
        concurrency_group="analytics",
        category="write",
    )
    assert p.max_steps == 50
    assert p.permission_mode == PermissionMode.BYPASS
    assert p.result_schema == {"type": "object"}
    assert p.concurrency_group == "analytics"
    assert p.category == "write"


# 功能：category 字段只接受 4 个合法字面量
# 设计：用 parametrize 验证 read/write/command/other 四类；非法值必须被构造期拒绝（dataclass 类型注解）
@pytest.mark.parametrize(
    "category", ["read", "write", "command", "other"]
)
def test_category_accepts_v1_literals(category: str) -> None:
    p = AgentProfile(name="x", category=category)  # type: ignore[arg-type]
    assert p.category == category


# 功能：description / system_prompt / allowed_tools / model 默认值与字段顺序保持向后兼容
# 设计：仅传 name 时 description="" / system_prompt="" / allowed_tools=[] / model=""；
#      这是 Wave 1 之前的 5 字段，必须保持原行为不破坏既有 .toml 解析
def test_legacy_fields_defaults_preserved() -> None:
    p = AgentProfile(name="x")
    assert p.description == ""
    assert p.system_prompt == ""
    assert p.allowed_tools == []
    assert p.model == ""


# 功能：TOML 解析时 5 个新字段被正确读出
# 设计：写一份带 v1 字段的 TOML，调用 _parse 解析，断言 5 字段值完整；
#      这是 C 阶段把 6 个业务 Profile 迁过来时的契约基础
def test_toml_parses_v1_fields(tmp_path: Path) -> None:
    content = """\
[agent]
description = "test"
system_prompt = "you are x"
allowed_tools = ["read_file"]
model = "claude-sonnet-4-6"
max_steps = 30
permission_mode = "plan"
result_schema = {"type" = "object", "properties" = {"answer" = {"type" = "string"}}}
concurrency_group = "rag_pool"
category = "read"
"""
    p = tmp_path / "x.toml"
    p.write_text(content, encoding="utf-8")
    loader = AgentProfileLoader()
    profile = loader._parse(p, "x")
    assert profile.max_steps == 30
    assert profile.permission_mode == PermissionMode.PLAN
    assert profile.result_schema == {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
    }
    assert profile.concurrency_group == "rag_pool"
    assert profile.category == "read"


# 功能：TOML 缺省 v1 字段时使用 dataclass 默认值
# 设计：只写 5 个旧字段，断言 5 个新字段都取默认值；这是向后兼容的关键
def test_toml_missing_v1_fields_uses_defaults(tmp_path: Path) -> None:
    content = """\
[agent]
description = "minimal"
system_prompt = "hi"
allowed_tools = []
model = ""
"""
    p = tmp_path / "min.toml"
    p.write_text(content, encoding="utf-8")
    loader = AgentProfileLoader()
    profile = loader._parse(p, "min")
    assert profile.max_steps == 20
    assert profile.permission_mode == PermissionMode.DEFAULT
    assert profile.result_schema is None
    assert profile.concurrency_group == "default"
    assert profile.category == "other"
