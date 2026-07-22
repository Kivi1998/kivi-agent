"""Skills 2.0 受控脚本执行：execute_skill_script。

三道防线（与 aigroup content_reader.py 对齐）：
1. 超时（subprocess.run timeout）
2. 输出大小截断（max_output_bytes）
3. 内存限制（POSIX RLIMIT_AS；Windows 已知缺口，warn 不阻断）

异常归一化：所有脚本异常都是 SkillScriptError；超时是 SkillTimeoutError 子类。
"""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# 内存限制默认 256MB（aigroup 用同量级）
DEFAULT_MAX_MEMORY_BYTES = 256 * 1024 * 1024


class SkillScriptError(Exception):
    """Skill 脚本执行失败的统一异常（含超时、退出码非零、内存超限）。"""

    def __init__(self, message: str, *, returncode: int | None, stderr: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class SkillTimeoutError(SkillScriptError):
    """Skill 脚本执行超时。"""

    def __init__(self, message: str, *, stderr: str = "") -> None:
        super().__init__(message, returncode=None, stderr=stderr)


# 受控执行 skill 脚本：subprocess + 超时 + 输出截断 + POSIX 内存限制
def execute_skill_script(
    script_path: Path,
    *,
    args: list[str] | None = None,
    timeout_s: float,
    max_output_bytes: int,
    max_memory_bytes: int | None = DEFAULT_MAX_MEMORY_BYTES,
) -> str:
    """执行 skill 脚本并返回 stdout（已截断到 max_output_bytes）。

    Args:
        script_path: 脚本绝对路径（python 解释器由 sys.executable 提供）
        args: 传给脚本的位置参数（不包含解释器与脚本路径本身）
        timeout_s: 超时秒数
        max_output_bytes: stdout 截断上限（0 = 完全截断）
        max_memory_bytes: RLIMIT_AS 上限（POSIX only；None 跳过；Windows 跳过）

    Returns:
        截断后的 stdout 字符串

    Raises:
        SkillTimeoutError: 执行超过 timeout_s
        SkillScriptError: 退出码非零 / 启动失败 / 内存超限被杀
    """
    argv = [sys.executable, str(script_path), *(args or [])]

    preexec_fn: Callable[[], object] | None = _build_preexec_fn(max_memory_bytes)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            preexec_fn=preexec_fn,
        )
    except subprocess.TimeoutExpired as e:
        raise SkillTimeoutError(
            f"script timed out after {timeout_s}s: {script_path.name}",
            stderr=(e.stderr or "") if isinstance(e.stderr, str) else (e.stderr or b"").decode(
                errors="replace"
            ),
        ) from e
    except FileNotFoundError as e:
        raise SkillScriptError(
            f"interpreter not found: {argv[0]}", returncode=None, stderr=str(e)
        ) from e

    if proc.returncode != 0:
        raise SkillScriptError(
            f"script exited with code {proc.returncode}: {script_path.name}",
            returncode=proc.returncode,
            stderr=proc.stderr,
        )

    return _truncate(proc.stdout, max_output_bytes, source=str(script_path))


# 构建 POSIX preexec_fn：设置 RLIMIT_AS
def _build_preexec_fn(max_memory_bytes: int | None) -> Callable[[], object] | None:
    if max_memory_bytes is None:
        return None
    if sys.platform == "win32":
        logger.warning("memory limit (RLIMIT_AS) is POSIX-only; skipped on Windows")
        return None

    import resource  # POSIX-only import; deferred to function scope

    def _preexec() -> None:
        # preexec_fn 异常会被 Python 3.12 包装成 SubprocessError 并隐藏原始错误，
        # 这里先 try/except + logger，避免主流程被一个非关键限制拖累
        try:
            resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
        except (ValueError, OSError) as e:
            logger.warning("failed to set RLIMIT_AS=%d: %s", max_memory_bytes, e)

    return _preexec


# 输出截断（带 warn）
def _truncate(text: str, max_bytes: int, *, source: str) -> str:
    if max_bytes <= 0:
        if text:
            logger.warning("script output truncated to 0 bytes: %s", source)
        return ""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) > max_bytes:
        logger.warning(
            "script output truncated: %s bytes %d > limit %d", source, len(encoded), max_bytes
        )
        return encoded[:max_bytes].decode("utf-8", errors="replace")
    return text
