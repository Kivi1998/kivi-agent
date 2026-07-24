"""tests.e2e_real.conftest 单元测试（agent: package-e2e-real-w82）。

# test_e2e_real_conftest.py（agent: package-e2e-real-w82）
覆盖 4 个纯函数：
- is_e2e_enabled：env guard 默认禁用 / 启用切
- resolve_provider_name：默认 anthropic / openai / 非法值
- resolve_max_cases：默认 5 / 非法值 / 负数
- resolve_report_dir：默认 reports/e2e_real/ / 绝对路径 / 空字符串

不依赖 pytest fixture（直接调纯函数），确保逻辑在 CI 与本地一致。
"""
from __future__ import annotations

import os
from pathlib import Path

# noqa: E402 — 被测模块需要在 os.environ 操作后 import
from tests.e2e_real.conftest import (  # noqa: E402
    is_e2e_enabled,
    resolve_max_cases,
    resolve_provider_name,
    resolve_report_dir,
)


# 功能：env guard 默认禁用
# 设计：不传 env 参数时读 os.environ；默认 KIVI_RUN_E2E 未设 → False
def test_is_e2e_enabled_default_false() -> None:
    """``KIVI_RUN_E2E`` 未设时返回 False。"""
    # 强制清掉全局 KIVI_RUN_E2E（其他测试可能设过）
    saved = os.environ.pop("KIVI_RUN_E2E", None)
    try:
        assert is_e2e_enabled() is False
    finally:
        if saved is not None:
            os.environ["KIVI_RUN_E2E"] = saved


# 功能：env guard 启用（KIVI_RUN_E2E=1）
# 设计：注入 {"KIVI_RUN_E2E": "1"} → True
def test_is_e2e_enabled_when_set() -> None:
    """``KIVI_RUN_E2E == "1"`` 时返回 True。"""
    assert is_e2e_enabled({"KIVI_RUN_E2E": "1"}) is True


# 功能：env guard 其他值不启用
# 设计："0" / "true" / "yes" / 空字符串都 → False
def test_is_e2e_enabled_rejects_other_values() -> None:
    """只有字符串 "1" 才启用；其他值（包括 "0" / "true" / ""）禁用。"""
    for v in ("0", "true", "yes", "", " 1 ", "1 "):
        assert is_e2e_enabled({"KIVI_RUN_E2E": v}) is False, f"unexpected: {v!r}"


# 功能：provider 默认 anthropic
def test_resolve_provider_name_default_anthropic() -> None:
    """``KIVI_E2E_PROVIDER`` 未设时返回 ``anthropic``。"""
    assert resolve_provider_name({}) == "anthropic"


# 功能：provider openai 显式
def test_resolve_provider_name_openai() -> None:
    """``KIVI_E2E_PROVIDER=openai`` → ``openai``。"""
    assert resolve_provider_name({"KIVI_E2E_PROVIDER": "openai"}) == "openai"


# 功能：provider 大小写归一化
def test_resolve_provider_name_case_insensitive() -> None:
    """``KIVI_E2E_PROVIDER=Anthropic`` → ``anthropic``（归一化小写）。"""
    assert resolve_provider_name({"KIVI_E2E_PROVIDER": "Anthropic"}) == "anthropic"
    assert resolve_provider_name({"KIVI_E2E_PROVIDER": "OPENAI"}) == "openai"


# 功能：provider 非法值回退 anthropic
def test_resolve_provider_name_invalid_falls_back() -> None:
    """非法值（如 ``mock``）回退到 ``anthropic``。"""
    assert resolve_provider_name({"KIVI_E2E_PROVIDER": "mock"}) == "anthropic"
    assert resolve_provider_name({"KIVI_E2E_PROVIDER": ""}) == "anthropic"


# 功能：max_cases 默认 5
def test_resolve_max_cases_default_5() -> None:
    """``KIVI_E2E_MAX_CASES`` 未设时返回 5。"""
    assert resolve_max_cases({}) == 5


# 功能：max_cases 显式整数
def test_resolve_max_cases_explicit_int() -> None:
    """``KIVI_E2E_MAX_CASES=3`` → 3。"""
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": "3"}) == 3


# 功能：max_cases 非法值回退 5
def test_resolve_max_cases_invalid_falls_back() -> None:
    """非整数（含空字符串、字母）回退 5。"""
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": "abc"}) == 5
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": ""}) == 5
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": "3.5"}) == 5


# 功能：max_cases 负数 / 0 兜底为 1
def test_resolve_max_cases_clamps_to_min_1() -> None:
    """``KIVI_E2E_MAX_CASES=0`` 或负数 → 至少 1。"""
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": "0"}) == 1
    assert resolve_max_cases({"KIVI_E2E_MAX_CASES": "-5"}) == 1


# 功能：report_dir 默认 reports/e2e_real/
def test_resolve_report_dir_default() -> None:
    """``KIVI_E2E_REPORT_DIR`` 未设时返回 ``<cwd>/reports/e2e_real/``。"""
    p = resolve_report_dir({})
    assert p.name == "e2e_real"
    assert p.parent.name == "reports"
    # 默认是相对路径经 cwd 拼接后变绝对路径
    assert p.is_absolute()
    assert p == Path.cwd() / "reports" / "e2e_real"


# 功能：report_dir 显式路径
def test_resolve_report_dir_explicit(tmp_path: Path) -> None:
    """``KIVI_E2E_REPORT_DIR`` 显式相对路径 → 拼接到 cwd。"""
    p = resolve_report_dir({"KIVI_E2E_REPORT_DIR": str(tmp_path / "custom")})
    assert p.name == "custom"
    assert p.parent == tmp_path


# 功能：report_dir 绝对路径直接返回
def test_resolve_report_dir_absolute() -> None:
    """绝对路径直接使用，不拼接 cwd。"""
    p = resolve_report_dir({"KIVI_E2E_REPORT_DIR": "/tmp/kivi-e2e-test"})
    assert p.is_absolute()
    assert str(p) == "/tmp/kivi-e2e-test"


# 功能：report_dir 空字符串回退默认
def test_resolve_report_dir_empty_falls_back() -> None:
    """``KIVI_E2E_REPORT_DIR=""`` 回退到默认 ``reports/e2e_real/``。"""
    p = resolve_report_dir({"KIVI_E2E_REPORT_DIR": ""})
    assert p.name == "e2e_real"


# 功能：resolve 函数不读全局 env（隔离测试用 env dict）
def test_resolve_functions_use_provided_env_only() -> None:
    """传入 env dict 时完全不读 os.environ，确保测试可重入。"""
    env = {
        "KIVI_RUN_E2E": "0",  # 即使全局是 1，这个 False
        "KIVI_E2E_PROVIDER": "openai",
        "KIVI_E2E_MAX_CASES": "10",
        "KIVI_E2E_REPORT_DIR": "/tmp/x",
    }
    assert is_e2e_enabled(env) is False
    assert resolve_provider_name(env) == "openai"
    assert resolve_max_cases(env) == 10
    assert str(resolve_report_dir(env)) == "/tmp/x"
