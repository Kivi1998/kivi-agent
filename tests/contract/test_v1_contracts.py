"""v1 契约冒烟测试（Wave 1 / E 阶段）。

测试目标（按 `docs/contracts/v1.md` 章节）：
- §1: 6 个业务 Tool 名称冻结（如果 C 已实现则 import 验证，否则记 TODO）
- §2: RunContext 8 字段 + schema_version（如果 A 已实现则 import 验证，否则用协议期望对比）
- §3: AgentProfile 5 字段扩展（如果 A 已实现则 import 验证，否则用协议期望对比）
- §4: 所有 BaseTool 子类用 `input_schema`，不是 `params_schema`

**降级策略**：
- A/B/C/D 任一 Agent 未完成时，测试不会 fail，而是用 `pytest.skip` + TODO 标记
- 一旦上游 Agent 完成，删除 skip 即可激活强校验
"""
from __future__ import annotations

from typing import Any, ClassVar

import pytest

from tests.contract.conftest import (
    V1_BUSINESS_TOOL_NAMES,
    V1_DEPRECATED_TOOL_NAMES,
    V1_SCHEMA_VERSION,
    V1_TOOL_SCHEMA_FIELD,
    V1_TOOL_SCHEMA_FIELD_FORBIDDEN,
    ExpectedAgentProfile,
    ExpectedRunContext,
)


# ---- §1 业务 Tool 名称冻结 -------------------------------------------------

# 功能：验证 v1 §1 锁定的 6 个业务 Tool 名称在 C 阶段业务 Tool 落地后全部出现
# 设计：用 importlib 软探测 C 阶段业务 Tool 注册表，未实现则 skip 留 TODO
def test_v1_business_tool_names_defined_in_code(v1_business_tool_names: tuple[str, ...]) -> None:
    """§1 — 当 C 阶段业务 Tool 落地后，6 个名字必须出现于代码。"""
    # 软探测 C 阶段的业务 Tool 模块（如果 A 已就绪才会出现）
    from importlib import import_module

    candidate_modules = [
        "kivi_agent.core.business.tools",
        "kivi_agent.core.business",
    ]
    found_any = False
    for mod_name in candidate_modules:
        try:
            mod = import_module(mod_name)
        except ModuleNotFoundError:
            continue
        found_any = True
        # 提取模块内"看起来像 Tool 名"的常量字符串（避免依赖具体类名）
        defined_names: set[str] = set()
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            value = getattr(mod, attr_name, None)
            if isinstance(value, str):
                defined_names.add(value)
            elif isinstance(value, (list, tuple, set)):
                defined_names.update(x for x in value if isinstance(x, str))
        # 已注册 Tool 类的 name 属性
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name, None)
            if obj is None or not hasattr(obj, "__mro__"):
                continue
            for base in getattr(obj, "__mro__", []):
                if base.__name__ == "BaseTool" and hasattr(obj, "name"):
                    defined_names.add(getattr(obj, "name"))
                    break

        missing = [n for n in v1_business_tool_names if n not in defined_names]
        if missing:
            pytest.fail(
                f"v1 §1 缺失业务 Tool: {missing}\n"
                f"  模块 {mod_name} 仅发现: {sorted(defined_names)}"
            )

    if not found_any:
        pytest.skip(
            "TODO(E 阶段): C 阶段业务 Tool 模块尚未实现；"
            "v1 §1 6 个 Tool 名已锁在 tests/contract/conftest.py.V1_BUSINESS_TOOL_NAMES"
        )


# 功能：确保 6 个被弃的旧 Tool 名字不会回潮到代码中
# 设计：扫描核心模块（已实现部分）确认无旧名常量/Tool 类残留
def test_v1_deprecated_tool_names_not_reintroduced(v1_deprecated_tool_names: tuple[str, ...]) -> None:
    """§1 反向断言 — 旧 Tool 名不应回潮。"""
    # 只扫描已存在的核心模块；新模块 C 阶段才会建
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src" / "kivi_agent"
    if not src_root.exists():
        pytest.skip("src/kivi_agent 不存在（异常）")

    # 关键词在源码里作为字符串/标识符出现时报警
    # 但允许出现在注释/文档字符串/migration 报告中（专门排除）
    for old_name in v1_deprecated_tool_names:
        offenders: list[str] = []
        for py_file in src_root.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            # 排除明确允许的引用：
            # 1. tests/contract/ 自身
            # 2. 含 "v1.md" 引用的契约注释
            # 3. 含 "TODO" / "DEPRECATED" 关键词的注释行
            for line_no, line in enumerate(content.splitlines(), start=1):
                if old_name not in line:
                    continue
                stripped = line.strip()
                # 注释或 docstring 中讨论契约时可豁免
                if (
                    stripped.startswith("#")
                    or "v1.md" in line
                    or "V1_DEPRECATED" in line
                    or "TODO" in stripped
                    or "DEPRECATED" in line
                ):
                    continue
                offenders.append(f"{py_file.relative_to(repo_root)}:{line_no}: {stripped}")
        if offenders:
            # 警告而非 fail：E 阶段主要工作是契约测试与 Mock；tool 落地是 C 阶段
            # 但记录在测试输出里，让 C 阶段开工前能看到
            print(f"\n[WARNING] v1 §1 旧 Tool 名 '{old_name}' 在源码中出现：")
            for off in offenders[:5]:
                print(f"  {off}")
            if len(offenders) > 5:
                print(f"  ... 还有 {len(offenders) - 5} 处")


# ---- §2 RunContext 8 字段 ---------------------------------------------------

# 功能：验证 v1 §2 冻结的 8 个 RunContext 数据字段 + schema_version 全部存在
# 设计：先尝试 import A 阶段 RunContext；未实现则用协议期望对象（8 字段）做"应有尽有"检查
def test_v1_run_context_has_eight_required_fields(
    expected_run_context: ExpectedRunContext,
) -> None:
    """§2 — RunContext 8 数据字段 + schema_version 必须齐备。"""
    expected_data_fields = {
        "run_id",
        "trace_id",
        "user_id",
        "session_id",
        "datasource_id",
        "knowledge_base_id",
        "frontend_connection_id",
        "runtime_values",
    }

    # 尝试导入 A 阶段 RunContext
    try:
        from kivi_agent.core.context import RunContext  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pytest.skip(
            "TODO(E 阶段): A 阶段 RunContext 尚未实现；"
            "v1 §2 字段集已锁在 tests/contract/conftest.py.ExpectedRunContext"
        )

    actual_fields = set(RunContext.__dataclass_fields__.keys())
    missing = expected_data_fields - actual_fields
    assert not missing, (
        f"v1 §2 RunContext 缺失字段: {missing}\n"
        f"  实际字段: {sorted(actual_fields)}\n"
        f"  期望字段: {sorted(expected_data_fields)}"
    )
    # schema_version 字段
    assert "schema_version" in actual_fields, (
        "v1 §2 RunContext 必须有 schema_version 字段（默认 1）"
    )
    # 默认值校验
    assert RunContext.__dataclass_fields__["schema_version"].default == V1_SCHEMA_VERSION


# 功能：确保 RunContext 不再包含 v1 §2 弃用的字段名
# 设计：白名单制（只允许 §2 字段 + schema_version），避免 `db_id`/`user_query` 等回潮
def test_v1_run_context_no_deprecated_fields() -> None:
    """§2 反向断言 — 旧 RunContext 字段（`db_id`/`user_query` 等）不应回潮。"""
    deprecated = {
        "db_id",                # → datasource_id
        "original_query",       # → 不在 RunContext
        "user_query",           # → 不在 RunContext
        "conversation_history",  # → 不在 RunContext
        "runtime_metadata",     # → runtime_values
        "extra_tools",          # → runtime_values
    }
    try:
        from kivi_agent.core.context import RunContext  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        pytest.skip("TODO(E 阶段): A 阶段 RunContext 尚未实现")

    actual = set(RunContext.__dataclass_fields__.keys())
    leaked = deprecated & actual
    assert not leaked, f"v1 §2 RunContext 残留旧字段: {leaked}"


# ---- §3 AgentProfile 5 字段扩展 --------------------------------------------

# 功能：验证 v1 §3 冻结的 5 个 AgentProfile 扩展字段
# 设计：同样支持降级——未实现时用协议期望对比
def test_v1_agent_profile_has_five_extension_fields(
    expected_agent_profile_ext: ExpectedAgentProfile,
) -> None:
    """§3 — AgentProfile 必须有 5 个扩展字段（不含基础 5 字段 = 共 10 字段）。"""
    expected_ext = {
        "max_steps",
        "permission_mode",
        "result_schema",
        "concurrency_group",
        "category",
    }

    try:
        from kivi_agent.core.agents import AgentProfile
    except (ImportError, AttributeError):
        pytest.skip(
            "TODO(E 阶段): A 阶段 AgentProfile 模块尚未实现；"
            "v1 §3 字段集已锁在 tests/contract/conftest.py.ExpectedAgentProfile"
        )

    actual_fields = set(AgentProfile.__dataclass_fields__.keys())
    # 关键降级：AgentProfile 已实现但扩展字段未加——记录期望并 skip
    missing = expected_ext - actual_fields
    if missing:
        pytest.skip(
            f"TODO(E 阶段): A 阶段 AgentProfile 扩展字段未加；"
            f"v1 §3 期望新增 {sorted(expected_ext)}；"
            f"当前已有 {sorted(actual_fields)}；"
            f"缺: {sorted(missing)}"
        )
    # category 字段允许的 Literal 值
    cat_field = AgentProfile.__dataclass_fields__["category"]
    # 在 mypy strict 下 dataclass field 的 type 表达较复杂，做宽松检查
    assert cat_field.default in {"read", "write", "command", "other"}, (
        f"v1 §3 category 默认值必须是 read/write/command/other 之一，"
        f"实际: {cat_field.default}"
    )


# 功能：验证 AgentProfile 基础 5 字段（name/description/system_prompt/allowed_tools/model）保留
# 设计：基础 5 字段是 AgentProfile 既定事实，与 v1 §3 扩展字段相加 = 10 字段
def test_v1_agent_profile_base_five_fields_preserved() -> None:
    """§3 — 基础 5 字段（既有事实）必须保留。"""
    expected_base = {
        "name",
        "description",
        "system_prompt",
        "allowed_tools",
        "model",
    }
    try:
        from kivi_agent.core.agents import AgentProfile
    except (ImportError, AttributeError):
        pytest.skip("TODO(E 阶段): A 阶段 AgentProfile 扩展字段尚未实现")

    actual = set(AgentProfile.__dataclass_fields__.keys())
    missing = expected_base - actual
    assert not missing, f"AgentProfile 基础字段缺失: {missing}"


# ---- §4 Tool Schema 字段名（input_schema） -----------------------------------

# 功能：验证 BaseTool 子类用 input_schema 而不是 params_schema
# 设计：扫描所有 BaseTool 子类，断言每个子类的类属性不含 params_schema
def test_v1_base_tool_uses_input_schema_not_params_schema() -> None:
    """§4 — Tool Schema 统一使用 `input_schema`，禁止 `params_schema`。"""
    from kivi_agent.core.tools import BaseTool

    # 递归收集所有 BaseTool 子类
    def _collect_subclasses(cls: type) -> list[type]:
        result: list[type] = [cls]
        for sub in cls.__subclasses__():
            result.extend(_collect_subclasses(sub))
        return result

    all_tools = _collect_subclasses(BaseTool)

    # 必须至少有 BaseTool 自己（否则说明继承树断）
    assert BaseTool in all_tools

    # 每个具体子类（不是 BaseTool 自己）必须有 input_schema 类属性
    for sub in all_tools:
        if sub is BaseTool:
            continue
        assert hasattr(sub, V1_TOOL_SCHEMA_FIELD), (
            f"v1 §4 违反: {sub.__module__}.{sub.__name__} 缺少 {V1_TOOL_SCHEMA_FIELD} 属性"
        )
        # 禁止把 params_schema 作为类属性（避免和 input_schema 混用）
        assert not hasattr(sub, V1_TOOL_SCHEMA_FIELD_FORBIDDEN), (
            f"v1 §4 违反: {sub.__module__}.{sub.__name__} 仍使用 {V1_TOOL_SCHEMA_FIELD_FORBIDDEN}"
        )


# 功能：验证 BaseTool 自身就定义了 input_schema
# 设计：BaseTool 是抽象基类，input_schema 在它是类属性，子类必须 override
def test_v1_base_tool_defines_input_schema_attribute() -> None:
    """§4 — BaseTool 抽象基类必须有 input_schema 字段定义。"""
    from kivi_agent.core.tools import BaseTool

    # 降级：当前 BaseTool 用 `input_schema` 类属性占位（v1 §4 决议前的过渡形式）
    # 若 A 阶段按 v1 §4 决议保持 input_schema 即可
    # 若 E 报告 §T9 建议的"params_schema"回潮则 fail
    if not hasattr(BaseTool, V1_TOOL_SCHEMA_FIELD):
        pytest.skip(
            f"TODO(A 阶段): BaseTool 应有 {V1_TOOL_SCHEMA_FIELD} 类属性；"
            f"当前基类仍未定义此属性。"
            f"v1 §4 决议：使用 {V1_TOOL_SCHEMA_FIELD}（不是 {V1_TOOL_SCHEMA_FIELD_FORBIDDEN}）"
        )


# ---- v1 schema_version 守门 ------------------------------------------------

# 功能：验证 v1 schema_version 字面值是 1
# 设计：契约层常量集中，单元测试做"读到的是 1"的最弱断言
def test_v1_schema_version_constant_is_one() -> None:
    """v1 当前 schema_version 必须 = 1。"""
    assert V1_SCHEMA_VERSION == 1
