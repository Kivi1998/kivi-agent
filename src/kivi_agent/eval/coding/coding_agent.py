"""T12 最小 coding agent（agent: package-eval-coding-v52）。

# coding_agent.py（agent: package-eval-coding-v52）
kivi 内自建最小 coding agent（**不**接 aigroup，**不**接 langgraph）。
- 流程（per case）：
  1. 写 `case.initial_content` 到 sandbox 目录
  2. 循环 iter=1..max_iter：
     a. LLM 生成 patch / 全文件
     b. 应用到 sandbox 文件
     c. 跑 pytest 收集结果
     d. 全过 → 退出；否则 iter < max_iter 时把 pytest 输出喂回 LLM 继续
- 沙箱隔离：每次 `run_case` 用 `tempfile.TemporaryDirectory()`，绝不写主仓库
- LLM 注入式：构造时传 `LLMProvider`；单测用 `FakeLlmProvider`
- EventBus 注入式：构造时传 `EventBus`；单测用 `FakeEventBus`
"""
from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from kivi_agent.eval.coding.diff_parser import Hunk, parse_unified_diff
from kivi_agent.eval.coding.models import (
    CodingCase,
    CodingEvalResult,
    PatchRecord,
    TestRunRecord,
)


# 任何有 chat() 方法的对象（兼容 LLMProvider / FakeLlmProvider）
class _LlmLike(Protocol):
    """LLM 协议（duck-typed on `chat`，兼容 LLMProvider / FakeLlmProvider）。"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: Any,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> Any: ...


# 任何有 publish() 方法的对象（兼容 EventBus / FakeEventBus）
class _BusLike(Protocol):
    """EventBus 协议（duck-typed on `publish`）。"""

    async def publish(self, event: Any) -> None: ...


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# system prompt 模板（agent: package-eval-coding-v52）
_CODING_SYSTEM_PROMPT = (
    "You are an expert Python developer. "
    "Given a task description, a test file, and the current contents of a source file, "
    "produce EITHER a unified diff (starting with '@@') OR the full new contents of the source file. "
    "Do not include explanations. Output only the patch or the new file content."
)


# 在 sandbox 中跑单 case 的最小 coding agent（agent: package-eval-coding-v52）
class CodingAgent:
    """最小 coding agent（kivi 内，**不**接 aigroup）。

    参数：
        llm: LLMProvider（注入式；单测用 FakeLlmProvider）
        max_iter: 每 case 最大循环轮次（默认 3）
        bus: EventBus（注入式；单测用 FakeEventBus；默认 None 走哑总线）
    """

    def __init__(
        self,
        llm: _LlmLike,
        max_iter: int = 3,
        bus: _BusLike | None = None,
    ) -> None:
        if max_iter < 1:
            raise ValueError(f"max_iter must be >= 1, got {max_iter}")
        self._llm = llm
        self._max_iter = max_iter
        self._bus = bus

    # 跑单 case，返回 CodingEvalResult
    async def run_case(
        self, case: CodingCase, sandbox: Path | None = None
    ) -> CodingEvalResult:
        """跑单 case；返回 CodingEvalResult。

        sandbox 参数：可选；为 None 时内部用 `tempfile.TemporaryDirectory()`。
        调用方传 sandbox 时**必须**是临时目录（不能传主仓库路径）。
        """
        result = CodingEvalResult(case_id=case.id, started_at=_now_iso())
        # 沙箱隔离：每次 case 用独立临时目录
        own_tempdir: tempfile.TemporaryDirectory[str] | None = None
        if sandbox is None:
            own_tempdir = tempfile.TemporaryDirectory(prefix="kivi-coding-")
            sb = Path(own_tempdir.name)
        else:
            sb = sandbox
        try:
            await self._run_in_sandbox(case, sb, result)
        finally:
            if own_tempdir is not None:
                own_tempdir.cleanup()
        result.finished_at = _now_iso()
        return result

    # 在指定 sandbox 里跑循环（agent: package-eval-coding-v52）
    async def _run_in_sandbox(
        self, case: CodingCase, sandbox: Path, result: CodingEvalResult
    ) -> None:
        # 1. 路径遍历保护：拒绝任何含 ".." 的 case 路径
        if ".." in Path(case.initial_file).parts or ".." in Path(case.test_file).parts:
            raise ValueError(f"path traversal not allowed: {case.initial_file} / {case.test_file}")
        # 2. 写初始文件 + 测试文件
        initial_path = sandbox / case.initial_file
        test_path = sandbox / case.test_file
        initial_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.parent.mkdir(parents=True, exist_ok=True)
        initial_path.write_text(case.initial_content, encoding="utf-8")
        test_path.write_text(case.test_content, encoding="utf-8")

        prev_passed = 0
        prev_total = 0
        for it in range(1, self._max_iter + 1):
            # 3. 调 LLM 拿 patch
            current_content = (
                initial_path.read_text(encoding="utf-8") if initial_path.exists() else ""
            )
            messages = _build_messages(
                case=case,
                current_content=current_content,
                prev_test_output=result.test_runs[-1].output if result.test_runs else "",
            )
            run_id = f"coding-{uuid.uuid4().hex[:8]}"
            resp = await self._llm.chat(
                messages=messages,
                tool_schemas=[],
                bus=self._bus if self._bus is not None else _SilentBus(),
                run_id=run_id,
                step=it,
                system=_CODING_SYSTEM_PROMPT,
            )
            llm_text = getattr(resp, "text", "") or ""

            # 4. 应用 patch 到 sandbox
            new_content, hunk_count, applied_count, diff_text = _apply_llm_output(
                llm_text=llm_text, current_content=current_content
            )
            initial_path.write_text(new_content, encoding="utf-8")
            result.patches.append(
                PatchRecord(
                    iter=it,
                    hunk_count=hunk_count,
                    applied_count=applied_count,
                    diff_text=diff_text,
                )
            )

            # 5. 跑 pytest
            tr = await _run_pytest(sandbox=sandbox, test_path=test_path, iter_no=it)
            result.test_runs.append(tr)
            result.iteration_count = it
            result.final_passed = tr.passed

            # 6. 自愈计数：上一轮失败、本轮通过数提升 = 一次自愈
            #    注意：放在 success break 之前，否则 fail→pass 的恢复会被吞掉
            if result.test_runs and len(result.test_runs) >= 2:
                prev = result.test_runs[-2]
                if prev.passed < prev.total and tr.passed > prev.passed:
                    result.recovery_count += 1

            # 7. 全过 → 成功退出
            if tr.passed == tr.total and tr.total > 0:
                result.success = True
                break

            prev_passed = tr.passed
            prev_total = tr.total
            # 静默 unused 警告（保留 prev_* 为扩展自愈指标用）
            _ = (prev_passed, prev_total)

    # 暴露 max_iter 供测试断言
    @property
    def max_iter(self) -> int:
        """当前 agent 的最大循环轮次。"""
        return self._max_iter


# ---------------------------------------------------------------------------
# 辅助：构建 prompt 消息
# ---------------------------------------------------------------------------


# 构建 LLM 调用的 messages 列表（agent: package-eval-coding-v52）
def _build_messages(
    case: CodingCase, current_content: str, prev_test_output: str
) -> list[dict[str, object]]:
    """构造 LLM chat 调用的 messages。"""
    user_text = (
        f"Task:\n{case.task}\n\n"
        f"Expected function: {case.expected_function}\n\n"
        f"Current contents of `{case.initial_file}`:\n"
        f"```python\n{current_content}\n```\n\n"
        f"Test file `{case.test_file}`:\n"
        f"```python\n{case.test_content}\n```\n"
    )
    if prev_test_output:
        user_text += (
            f"\nPrevious test output (iteration failed):\n"
            f"```\n{prev_test_output[:2000]}\n```\n"
        )
    user_text += (
        "\nRespond with either a unified diff (starting with '@@') or the full new file content."
    )
    return [{"role": "user", "content": user_text}]


# ---------------------------------------------------------------------------
# 辅助：应用 LLM 输出（diff 或全文件）到 sandbox
# ---------------------------------------------------------------------------


# 应用 LLM 输出到当前文件内容；返回 (新内容, hunks_proposed, hunks_applied, diff_text)
def _apply_llm_output(
    llm_text: str, current_content: str
) -> tuple[str, int, int, str]:
    """应用 LLM 输出：unified diff → 应用 hunks；否则 → 全文件替换。

    返回 `(new_content, hunk_count, applied_count, diff_text)`：
    - hunk_count：解析出的 hunk 数（whole-file replace 时 = 1）
    - applied_count：成功应用的 hunk 数
    - diff_text：实际写入文件的 unified diff（whole-file replace 时 = 生成的 diff）
    """
    hunks = parse_unified_diff(llm_text)
    if hunks:
        new_content, applied = _apply_hunks(current_content, hunks)
        diff_text = llm_text
        return new_content, len(hunks), applied, diff_text
    # 否则视为全文件替换
    new_content = _strip_code_fence(llm_text)
    diff_text = _make_whole_file_diff(new_content)
    # 解析回 hunk 数（防御性：1）
    return new_content, 1, 1, diff_text


# 从 markdown 代码块里剥出纯代码（agent: package-eval-coding-v52）
def _strip_code_fence(text: str) -> str:
    """剥掉 ```python ... ``` 之类的围栏（保留尾部换行）。"""
    stripped = text.strip()
    m = re.match(r"^```(?:[a-zA-Z0-9_+\-]*)\n(.*?)\n?```\s*$", stripped, flags=re.DOTALL)
    if m:
        body = m.group(1)
        # 保留原文本的尾部换行习惯（围栏代码块通常以 \n 收尾）
        if text.endswith("\n") and not body.endswith("\n"):
            return body + "\n"
        return body
    # 无围栏：保留尾部换行（stripped 已去尾 \n，按 text 原习惯恢复）
    if text.endswith("\n") and not stripped.endswith("\n"):
        return stripped + "\n"
    return stripped


# 生成"全文件替换"形式的 unified diff（agent: package-eval-coding-v52）
def _make_whole_file_diff(new_content: str) -> str:
    """生成新增整文件的 unified diff（old 为空）。"""
    new_lines = new_content.splitlines() or [""]
    header = "@@ -0,0 +1,{} @@".format(len(new_lines))
    body = "\n".join("+" + ln for ln in new_lines)
    return f"{header}\n{body}\n"


# 把 hunk 列表应用到 current_content；返回 (new_content, applied_count)
def _apply_hunks(current_content: str, hunks: list[Hunk]) -> tuple[str, int]:
    """逐个 hunk 应用到 current_content；返回 (新内容, 成功数)。

    算法（最小版）：
    - 按 hunk.old_start 在 current_content 中定位（1-indexed）
    - 把 hunk 的 +/-/空格 行拼成"期望匹配"和"替换"两段
    - 完全匹配 → 替换；否则记为失败（不抛错）
    """
    lines = current_content.splitlines()
    applied = 0
    # 按 old_start 升序、倒序应用（避免后续行号偏移）
    ordered = sorted(hunks, key=lambda h: h.old_start, reverse=True)
    for h in ordered:
        # 提取 hunk 中的 old/new 段
        old_block: list[str] = []
        new_block: list[str] = []
        for ln in h.lines:
            if not ln:
                continue
            head = ln[0]
            body = ln[1:]
            if head == " ":
                old_block.append(body)
                new_block.append(body)
            elif head == "-":
                old_block.append(body)
            elif head == "+":
                new_block.append(body)
        # 1-indexed → 0-indexed
        start_idx = max(h.old_start - 1, 0)
        end_idx = start_idx + len(old_block)
        actual_block = lines[start_idx:end_idx]
        if actual_block == old_block:
            lines = lines[:start_idx] + new_block + lines[end_idx:]
            applied += 1
    return "\n".join(lines), applied


# ---------------------------------------------------------------------------
# 辅助：在 sandbox 中跑 pytest
# ---------------------------------------------------------------------------


# 清掉 sandbox 下所有 __pycache__ 目录（强制 pytest 重 import 源文件）
def _clear_pycache(sandbox: Path) -> None:
    """递归删除 sandbox 下所有 __pycache__ 目录。"""
    for cache in sandbox.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
    # .pytest_cache 也清掉，避免收集阶段读到旧 fixture
    pytest_cache = sandbox / ".pytest_cache"
    if pytest_cache.exists():
        shutil.rmtree(pytest_cache, ignore_errors=True)


# 跑 pytest 收集 passed/total + 输出（agent: package-eval-coding-v52）
async def _run_pytest(
    sandbox: Path, test_path: Path, iter_no: int
) -> TestRunRecord:
    """在 sandbox 中跑 pytest；返回 TestRunRecord。"""
    started = time.time()
    # 相对 sandbox 的路径（含子目录如 tests/test_add.py）
    rel_test = test_path.relative_to(sandbox).as_posix()
    # 清掉 __pycache__ 强制重新 import 源文件（不然第二轮 pytest 用旧 .pyc）
    _clear_pycache(sandbox)
    try:
        proc = await asyncio.create_subprocess_exec(
            "python",
            "-m",
            "pytest",
            rel_test,
            "-q",
            "--tb=line",
            "--no-header",
            cwd=str(sandbox),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        # python/pytest 不可用（如 CI 无 pytest）
        return TestRunRecord(
            iter=iter_no,
            passed=0,
            total=0,
            duration_seconds=time.time() - started,
            output=f"pytest not available: {exc}",
        )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return TestRunRecord(
            iter=iter_no,
            passed=0,
            total=0,
            duration_seconds=time.time() - started,
            output="pytest timeout",
        )
    output = (stdout_b + stderr_b).decode("utf-8", errors="replace")
    passed, total = _parse_pytest_summary(output)
    return TestRunRecord(
        iter=iter_no,
        passed=passed,
        total=total,
        duration_seconds=time.time() - started,
        output=output,
    )


# 从 pytest 输出里抠出 "X passed" / "X failed, Y passed" 统计
def _parse_pytest_summary(output: str) -> tuple[int, int]:
    """解析 pytest summary 行：返回 (passed, total)。

    容错：找不到时返回 (0, 0)；total 取 passed + failed。
    """
    # 例： "1 failed, 2 passed in 0.05s"
    m = re.search(r"(\d+)\s+passed", output)
    passed = int(m.group(1)) if m else 0
    fm = re.search(r"(\d+)\s+failed", output)
    failed = int(fm.group(1)) if fm else 0
    em = re.search(r"(\d+)\s+error", output)
    errors = int(em.group(1)) if em else 0
    total = passed + failed + errors
    if total == 0 and "passed" not in output:
        return 0, 0
    return passed, total


# ---------------------------------------------------------------------------
# SilentBus：默认 bus 占位（避免单测必须传 FakeEventBus）
# ---------------------------------------------------------------------------


class _SilentBus:
    """哑 EventBus：什么都不发布。"""

    async def publish(self, event: Any) -> None:  # noqa: ARG002
        return None
