from __future__ import annotations

from kivi_agent.core.context.run_context import RunContext


# 功能：必填字段全部填齐时 RunContext 能正常构造
# 设计：按 v1 §2 表格填齐 4 个必填字段，断言 4 字段值原样保留（字段名冻结见 v1 §2）
def test_required_fields_construct() -> None:
    rc = RunContext(
        run_id="r-1",
        trace_id="t-1",
        user_id="u-1",
        session_id="s-1",
    )
    assert rc.run_id == "r-1"
    assert rc.trace_id == "t-1"
    assert rc.user_id == "u-1"
    assert rc.session_id == "s-1"


# 功能：schema_version 字段默认值为 1
# 设计：不传 schema_version 构造，断言 == 1；这是 v1 契约冻结点，未来升级到 v2 必走 ADR
def test_schema_version_default_is_1() -> None:
    rc = RunContext(
        run_id="r-1", trace_id="t-1", user_id="u-1", session_id="s-1"
    )
    assert rc.schema_version == 1


# 功能：runtime_values 字段默认值为空 dict（非 None）
# 设计：构造后断言是 dict 且为空，避免调用方写 NoneType 检查
def test_runtime_values_default_is_empty_dict() -> None:
    rc = RunContext(
        run_id="r-1", trace_id="t-1", user_id="u-1", session_id="s-1"
    )
    assert rc.runtime_values == {}
    assert isinstance(rc.runtime_values, dict)


# 功能：3 个可选 ID 字段默认值为 None
# 设计：分别断言 datasource_id / knowledge_base_id / frontend_connection_id 默认 None，
#      这是 v1 表格"可选"列的契约，必须明确为 None 以便业务 Tool 做空值判断
def test_optional_id_fields_default_none() -> None:
    rc = RunContext(
        run_id="r-1", trace_id="t-1", user_id="u-1", session_id="s-1"
    )
    assert rc.datasource_id is None
    assert rc.knowledge_base_id is None
    assert rc.frontend_connection_id is None


# 功能：3 个可选 ID 字段能正常赋值与读取
# 设计：构造时传入非 None 值，断言字段值完整保留；这是 C 阶段（datasource_id 注入 query_database）、
#      D 阶段（frontend_connection_id 注入 Web）的公共契约基础
def test_optional_id_fields_assignable() -> None:
    rc = RunContext(
        run_id="r-1",
        trace_id="t-1",
        user_id="u-1",
        session_id="s-1",
        datasource_id="ds-7",
        knowledge_base_id="kb-3",
        frontend_connection_id="ws-99",
    )
    assert rc.datasource_id == "ds-7"
    assert rc.knowledge_base_id == "kb-3"
    assert rc.frontend_connection_id == "ws-99"


# 功能：runtime_values 能写入任意键值且实例间不共享
# 设计：两个实例分别写入不同键，断言互不污染；这是 v1 §2 表格"灵活扩展"列的契约，
#      default_factory 必须新建 dict，验证实例隔离
def test_runtime_values_independent_per_instance() -> None:
    rc1 = RunContext(
        run_id="r-1", trace_id="t-1", user_id="u-1", session_id="s-1"
    )
    rc2 = RunContext(
        run_id="r-2", trace_id="t-2", user_id="u-1", session_id="s-1"
    )
    rc1.runtime_values["key_a"] = 1
    rc2.runtime_values["key_b"] = 2
    assert rc1.runtime_values == {"key_a": 1}
    assert rc2.runtime_values == {"key_b": 2}


# 功能：schema_version 字段能显式覆盖为其他整数
# 设计：构造时显式传 schema_version=2，断言生效；这是 v2 升级路径的入口
def test_schema_version_can_be_overridden() -> None:
    rc = RunContext(
        run_id="r-1",
        trace_id="t-1",
        user_id="u-1",
        session_id="s-1",
        schema_version=2,
    )
    assert rc.schema_version == 2
