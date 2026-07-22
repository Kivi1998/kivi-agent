"""schema_version 守门（Wave 1 / E 阶段）。

v1 契约（`docs/contracts/v1.md`）明确：
- 任何 dataclass / 数据模型有 `schema_version` 字段，默认 1
- 修改契约必须升级 schema_version，并通过 ADR

本模块提供：
- `current_schema_version()`：返回当前 v1 字面值（= 1）
- `assert_schema_version(actual, expected, name)`：守门入口，
  期望 == 实际时通过，否则抛 `ContractVersionMismatchError`

**设计要点**（与 E 报告 T5 一致）：
- **可观测**：错误消息清晰，列出"实际 vs 期望 + 类名 + 升级方向"
- **失败可见**：抛 `ContractVersionMismatchError`（继承 ValueError，pytest 友好）
- **单一来源**：所有 v1 字面量从这里导出，不在多处硬编码
"""
from __future__ import annotations

#: 当前契约 schema 版本（v1 冻结）
_V1: int = 1


# 返回当前 schema 版本（演示版固定为 1）
def current_schema_version() -> int:
    """当前契约 schema 版本（v1 = 1）。"""
    return _V1


# schema_version 不匹配异常
class ContractVersionMismatchError(ValueError):
    """schema_version 不匹配异常。

    继承 ValueError 让 pytest 友好（assert 失败语义一致）。
    """


# 守门：检查 actual 与 expected 一致，否则抛清晰错误
def assert_schema_version(actual: int, expected: int, name: str) -> None:
    """检查实际 schema 版本与期望一致。

    参数：
        actual: 实际读到的 schema_version
        expected: 期望的 schema_version
        name: 数据类名（用于错误信息；如 "RunContext" / "TraceEnvelope"）

    异常：
        ContractVersionMismatchError: actual != expected
    """
    if actual == expected:
        return
    hint = (
        f"\n  提示：'{name}' schema_version={actual}，但当前代码期望 {expected}。"
        f"\n  - 若 {actual} > {expected}：下游代码需要升级到新版（按 v{actual} 契约适配）"
        f"\n  - 若 {actual} < {expected}：上游代码落后，需按 docs/contracts/v1.md 升级"
        f"\n  详见 docs/contracts/v1.md §9 修改契约的流程（需先写 ADR）"
    )
    raise ContractVersionMismatchError(
        f"schema_version 不匹配: {name}.schema_version={actual}, expected={expected}.{hint}"
    )
