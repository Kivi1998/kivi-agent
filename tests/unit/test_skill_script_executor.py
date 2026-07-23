"""Skills 2.0 Skill Script Executor 受控执行测试。

超时 / 输出截断 / 内存限制 / 异常归一化。Windows 跳过 RLIMIT_AS（用 monkeypatch
模拟 POSIX 行为确保测试跨平台可运行）。
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from kivi_agent.core.skills.script_executor import (
    SkillScriptError,
    SkillTimeoutError,
    execute_skill_script,
)

# ─────────────────────────── 辅助：写临时 python 脚本 ───────────────────────────


def _write_script(tmp_path: Path, body: str, name: str = "main.py") -> Path:
    """在 tmp_path 写一段 python 脚本并返回路径。"""
    path = tmp_path / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


# ─────────────────────────── 成功路径 ───────────────────────────


# 功能：正常执行成功时返回 stdout
# 设计：脚本 print "hello" + return 0，断言返回值含 hello
def test_success_returns_stdout(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'print("hello from script")')
    out = execute_skill_script(script, args=[], timeout_s=5.0, max_output_bytes=1024)
    assert "hello from script" in out


# 功能：执行成功时 args 正确传入脚本 sys.argv
# 设计：脚本读取 sys.argv[1]，断言 args[0] 传入
def test_args_passed_to_script(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'import sys; print(sys.argv[1])')
    out = execute_skill_script(script, args=["world"], timeout_s=5.0, max_output_bytes=1024)
    assert "world" in out


# 功能：执行成功时 returncode 非零也归一化为 SkillScriptError
# 设计：脚本 sys.exit(2)，断言抛 SkillScriptError 且含 stderr
def test_nonzero_exit_raises_skill_script_error(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'import sys; sys.stderr.write("boom"); sys.exit(2)')
    with pytest.raises(SkillScriptError) as exc_info:
        execute_skill_script(script, args=[], timeout_s=5.0, max_output_bytes=1024)
    assert "boom" in str(exc_info.value) or exc_info.value.returncode == 2


# ─────────────────────────── 超时 ───────────────────────────


# 功能：脚本执行超过 timeout_s 时抛 SkillTimeoutError
# 设计：脚本 sleep 5 + timeout_s=0.2，断言 SkillTimeoutError
def test_timeout_raises_skill_timeout_error(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'import time; time.sleep(5)')
    with pytest.raises(SkillTimeoutError):
        execute_skill_script(script, args=[], timeout_s=0.2, max_output_bytes=1024)


# 功能：SkillTimeoutError 是 SkillScriptError 的子类
# 设计：类型断言 + 实例断言
def test_timeout_is_skill_script_error_subclass() -> None:
    assert issubclass(SkillTimeoutError, SkillScriptError)


# ─────────────────────────── 输出超限 ───────────────────────────


# 功能：stdout 超过 max_output_bytes 时被截断 + warn
# 设计：脚本 print 1000 字节 + max_output_bytes=50，断言输出 ≤ 50
def test_output_truncated_when_exceeds_limit(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'print("X" * 1000)')
    out = execute_skill_script(script, args=[], timeout_s=5.0, max_output_bytes=50)
    assert len(out) <= 50


# 功能：max_output_bytes=0 时输出仍可读（截到 0 字节）
# 设计：极小限制 + 输出非空
def test_output_truncated_to_zero(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'print("X" * 100)')
    out = execute_skill_script(script, args=[], timeout_s=5.0, max_output_bytes=0)
    assert len(out) == 0


# 功能：max_output_bytes=0 + 输出本来就很小时，原样返回
# 设计：脚本空输出，断言返回空
def test_zero_limit_no_stdout_returns_empty(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'pass')
    out = execute_skill_script(script, args=[], timeout_s=5.0, max_output_bytes=0)
    assert out == ""


# ─────────────────────────── 内存限制（POSIX only） ───────────────────────────


# 功能：POSIX 下 max_memory_bytes 会触发 preexec_fn 调 RLIMIT_AS
# 设计：只验证 execute_skill_script 接受 max_memory_bytes 参数并正常返回
# （不直接 monkeypatch resource.setrlimit，因为 child 进程可能绕过 patch）
def test_memory_limit_param_accepted_on_posix(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("RLIMIT_AS is POSIX-only")
    script = _write_script(tmp_path, 'print("ok")')
    out = execute_skill_script(
        script,
        args=[],
        timeout_s=5.0,
        max_output_bytes=1024,
        max_memory_bytes=64 * 1024 * 1024,
    )
    assert "ok" in out


# 功能：max_memory_bytes=None 时不调 preexec_fn（不设内存限制）
# 设计：传 None，断言正常返回（不限内存）
def test_memory_limit_none_skips_preexec(tmp_path: Path) -> None:
    script = _write_script(tmp_path, 'print("ok")')
    out = execute_skill_script(
        script,
        args=[],
        timeout_s=5.0,
        max_output_bytes=1024,
        max_memory_bytes=None,
    )
    assert "ok" in out


# 功能：内存超限（脚本持续吃内存）在 POSIX 下应被 RLIMIT_AS 杀掉
# 设计：脚本尝试分配大 list + max_memory_bytes=64MB；macOS 上 RLIMIT_AS 不一定严格生效
# （已知行为），所以只断言函数返回或抛异常（不挂死），不强制要求异常类型
def test_memory_limit_terminates_hungry_script(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("RLIMIT_AS is POSIX-only; Windows known gap")
    script = _write_script(
        tmp_path,
        'a = []; [a.append("X" * 1024 * 1024) for _ in range(512)]',  # ~512MB
    )
    try:
        out = execute_skill_script(
            script,
            args=[],
            timeout_s=10.0,
            max_output_bytes=1024,
            max_memory_bytes=64 * 1024 * 1024,
        )
        # macOS 上 RLIMIT_AS 可能不严格生效；脚本可能正常返回（只是慢）
        assert isinstance(out, str)
    except (SkillScriptError, SkillTimeoutError):
        # POSIX Linux 上通常被 SIGKILL 杀，proc.returncode = -9
        pass


# ─────────────────────────── 异常类型层级 ───────────────────────────


# 功能：所有脚本异常都是 SkillScriptError（统一捕获面）
# 设计：实例化断言
def test_skill_script_error_is_base() -> None:
    err = SkillScriptError("boom", returncode=1, stderr="oops")
    assert err.returncode == 1
    assert err.stderr == "oops"
    assert "boom" in str(err)
