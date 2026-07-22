"""Contract version 守门单元测试（Wave 1 / E 阶段 T5）。

目标：
1. 验证 `current_schema_version()` 稳定返回 1
2. 验证 `assert_schema_version` 在匹配/不匹配两种情况下行为正确
3. 验证 `ContractVersionMismatchError` 是 ValueError 子类（pytest 友好）
4. 验证错误信息含清晰指引（类名 + actual/expected + ADR 引导）
5. 验证 dataclass/Pydantic 集成的可工作流（演示版：用 dataclass 模拟 RunContext）
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from kivi_agent.evaluation.contract_version import (
    ContractVersionMismatchError,
    assert_schema_version,
    current_schema_version,
)


# ---- 公共 API 守门 --------------------------------------------------------

# 功能：验证 current_schema_version() 持续返回 1（v1 冻结）
# 设计：直接断言字面值；任何 v2 升级必须改实现 + 改测试（fail-loud）
def test_current_schema_version_returns_one() -> None:
    assert current_schema_version() == 1


# 功能：验证 current_schema_version() 在多次调用下稳定
# 设计：避免实现里的随机/状态污染
def test_current_schema_version_is_stable() -> None:
    first = current_schema_version()
    second = current_schema_version()
    third = current_schema_version()
    assert first == second == third == 1


# ---- assert_schema_version 匹配路径 ----------------------------------------

# 功能：验证 assert_schema_version 匹配时通过
# 设计：传相同 int；不抛即通过
def test_assert_schema_version_passes_when_equal() -> None:
    # 不抛
    assert_schema_version(1, 1, "RunContext")
    assert_schema_version(2, 2, "TraceEnvelope")


# 功能：验证 assert_schema_version 对较大版本号也能匹配
# 设计：v2 / v3 升级时复用
def test_assert_schema_version_supports_higher_versions() -> None:
    assert_schema_version(2, 2, "RunContext")
    assert_schema_version(3, 3, "TraceEnvelope")
    assert_schema_version(10, 10, "Anything")


# ---- assert_schema_version 不匹配路径 --------------------------------------

# 功能：验证 actual < expected 时抛 ContractVersionMismatchError
# 设计：上游代码落后（schema_version=1）但当前代码要求 v2
def test_assert_schema_version_raises_when_actual_below_expected() -> None:
    with pytest.raises(ContractVersionMismatchError) as exc:
        assert_schema_version(1, 2, "RunContext")
    msg = str(exc.value)
    assert "RunContext" in msg
    assert "1" in msg
    assert "2" in msg


# 功能：验证 actual > expected 时抛 ContractVersionMismatchError
# 设计：上游代码超前（schema_version=3）但当前代码只懂 v2
def test_assert_schema_version_raises_when_actual_above_expected() -> None:
    with pytest.raises(ContractVersionMismatchError) as exc:
        assert_schema_version(3, 2, "TraceEnvelope")
    msg = str(exc.value)
    assert "TraceEnvelope" in msg
    assert "3" in msg
    assert "2" in msg


# 功能：验证错误信息含升级引导（ADR + docs/contracts/v1.md）
# 设计：开发者拿到错误能立刻知道下一步
def test_mismatch_error_message_includes_adr_guidance() -> None:
    with pytest.raises(ContractVersionMismatchError) as exc:
        assert_schema_version(2, 1, "RunContext")
    msg = str(exc.value)
    # 必须有可执行的引导
    assert "ADR" in msg or "adr" in msg.lower()
    assert "docs/contracts/v1.md" in msg


# 功能：验证 ContractVersionMismatchError 继承 ValueError
# 设计：pytest.assert 系列基于 ValueError；继承保证生态兼容
def test_mismatch_error_is_value_error() -> None:
    with pytest.raises(ValueError):
        assert_schema_version(2, 1, "X")


# ---- 演示版集成：dataclass + assert_schema_version ------------------------

# 功能：验证演示版典型用法——dataclass 模拟 RunContext，构造后用 assert 守门
# 设计：复刻 v1 §2 RunContext 的 schema_version 字段
@dataclass
class _DemoRunContext:
    schema_version: int = 1
    run_id: str = "r1"
    trace_id: str = "t1"


# 功能：验证 _DemoRunContext 构造后 schema_version=1，assert 通过
# 设计：覆盖完整的"建模 + 守门"工作流
def test_assert_schema_version_with_dataclass_instance() -> None:
    ctx = _DemoRunContext()
    assert ctx.schema_version == 1
    assert_schema_version(ctx.schema_version, current_schema_version(), "_DemoRunContext")


# 功能：验证 dataclass 故意设错 schema_version 时被拦截
# 设计：模拟"A 阶段设错 schema_version=2"被测试逮到
def test_assert_schema_version_catches_wrong_dataclass() -> None:
    ctx = _DemoRunContext(schema_version=99)

    with pytest.raises(ContractVersionMismatchError, match="99"):
        assert_schema_version(
            ctx.schema_version, current_schema_version(), "_DemoRunContext"
        )


# ---- 公共导出稳定性 -------------------------------------------------------

# 功能：验证 kivi_agent.evaluation 顶层包导出 ContractVersionMismatchError
# 设计：让上游 Agent 可以 `from kivi_agent.evaluation import ContractVersionMismatchError`
def test_evaluation_package_reexports_mismatch_error() -> None:
    import kivi_agent.evaluation as eval_pkg

    assert hasattr(eval_pkg, "ContractVersionMismatchError")
    assert eval_pkg.ContractVersionMismatchError is ContractVersionMismatchError
