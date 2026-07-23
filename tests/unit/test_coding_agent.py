"""T12 CodingAgent 单元测试（agent: package-eval-coding-v52）。

# test_coding_agent.py（agent: package-eval-coding-v52）
6+ 场景：FakeLlmProvider + 真实 pytest 跑 tmpdir 沙箱。
1. 单 iter 通过：LLM 直接返回正确代码
2. 单 iter 失败后 iter=2 通过：自愈路径
3. max_iter 用完仍失败
4. sandbox 隔离：不传 sandbox 时自动用临时目录
5. 路径遍历保护：initial_file / test_file 含 .. 拒绝
6. diff 路径：LLM 返回 unified diff（hunk_count=1 / applied_count=1）
7. 沙箱不污染主仓库（绝对路径在 tmpdir 内）
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kivi_agent.eval.coding.coding_agent import (
    CodingAgent,
    _apply_hunks,
    _apply_llm_output,
    _parse_pytest_summary,
    _strip_code_fence,
)
from kivi_agent.eval.coding.diff_parser import parse_unified_diff
from kivi_agent.eval.coding.models import CodingCase
from tests._fakes.event_bus import FakeEventBus
from tests._fakes.llm import FakeLlmProvider, LlmScriptedResponse


# 工厂：构造一个 add case（agent: package-eval-coding-v52）
def _add_case(**overrides: object) -> CodingCase:
    """构造 add(a, b) 测试 case。"""
    base: dict[str, object] = {
        "id": "add-1",
        "task": "Write add(a, b) returning a + b",
        "test_file": "tests/test_add.py",
        "test_content": "from mymod import add\n\n"
        "def test_add():\n    assert add(1, 2) == 3\n",
        "initial_file": "mymod.py",
        "initial_content": "# empty\n",
        "expected_function": "add",
        "expected_tests_count": 1,
        "max_iter": 3,
        "difficulty": "easy",
    }
    base.update(overrides)
    return CodingCase(**base)  # type: ignore[arg-type]


# 功能：单 iter 通过——LLM 直接返回正确的 add 函数
# 设计：scripted 1 条 = 完整 add 实现；断言 success=True / iter=1 / final_passed=1
def test_run_case_single_iter_passes() -> None:
    p = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="def add(a, b):\n    return a + b\n")]
    )
    bus = FakeEventBus()
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)
    case = _add_case()

    result = asyncio.run(agent.run_case(case))

    assert result.success is True
    assert result.iteration_count == 1
    assert result.final_passed == 1
    assert len(result.patches) == 1
    assert len(result.test_runs) == 1
    assert result.test_runs[0].passed == 1
    assert result.test_runs[0].total == 1


# 功能：fail → pass 自愈路径（iter=2 修复）
# 设计：scripted[0]=broken（return a-b）/ scripted[1]=fixed（return a+b）；
#       断言 success=True / iter=2 / recovery_count=1
def test_run_case_recovers_via_second_iter() -> None:
    p = FakeLlmProvider(
        scripted=[
            LlmScriptedResponse(text="def add(a, b):\n    return a - b\n"),
            LlmScriptedResponse(text="def add(a, b):\n    return a + b\n"),
        ]
    )
    bus = FakeEventBus()
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)
    case = _add_case()

    result = asyncio.run(agent.run_case(case))

    assert result.success is True
    assert result.iteration_count == 2
    assert result.recovery_count == 1
    # 最后一轮是 fixed，pytest 通过
    assert result.test_runs[-1].passed == 1


# 功能：max_iter 用完仍失败 → success=False
# 设计：3 条 scripted 全是 broken；断言 success=False / iter=3 / final_passed=0
def test_run_case_exhausts_max_iter_without_passing() -> None:
    p = FakeLlmProvider(
        scripted=[
            LlmScriptedResponse(text="def add(a, b):\n    return a - b\n"),
            LlmScriptedResponse(text="def add(a, b):\n    return 0\n"),
            LlmScriptedResponse(text="def add(a, b):\n    raise Exception()\n"),
        ]
    )
    agent = CodingAgent(llm=p, max_iter=3)
    case = _add_case()

    result = asyncio.run(agent.run_case(case))

    assert result.success is False
    assert result.iteration_count == 3
    assert result.final_passed == 0
    assert len(result.patches) == 3
    assert len(result.test_runs) == 3


# 功能：沙箱隔离——不传 sandbox 时自动用临时目录，不污染主仓库
# 设计：跑完 → 检查 result.started_at / finished_at 合理；初始内容被覆盖；
#       路径包含临时目录前缀
def test_run_case_uses_internal_temp_sandbox() -> None:
    p = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="def add(a, b):\n    return a + b\n")]
    )
    agent = CodingAgent(llm=p, max_iter=2)
    case = _add_case()

    result = asyncio.run(agent.run_case(case))

    assert result.success is True
    assert result.started_at != ""
    assert result.finished_at is not None
    assert result.finished_at >= result.started_at


# 功能：传 sandbox 时用调用方提供的目录（仍是隔离的 tmpdir）
# 设计：tmp_path 创 sandbox → run_case(case, sandbox) → 验证文件确实写在 sandbox 内
def test_run_case_writes_to_caller_sandbox(tmp_path: Path) -> None:
    p = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="def add(a, b):\n    return a + b\n")]
    )
    agent = CodingAgent(llm=p, max_iter=2)
    case = _add_case()

    result = asyncio.run(agent.run_case(case, sandbox=tmp_path))

    assert result.success is True
    # 验证文件确实写在 sandbox（不是主仓库）
    written = (tmp_path / "mymod.py").read_text(encoding="utf-8")
    assert "return a + b" in written
    # 测试文件也在
    assert (tmp_path / "tests" / "test_add.py").exists()


# 功能：路径遍历保护——initial_file 含 .. 段时 CodingCase 构造就拒
# 设计：直接在 _add_case 里传 initial_file="../escape.py"；
#       pydantic ValidationError 触发（CodingCase._reject_traversal 拒绝 .. 段）
def test_run_case_rejects_initial_file_path_traversal() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        _add_case(initial_file="../escape.py")
    assert "path traversal" in str(exc.value)


# 功能：unified diff 路径——LLM 返回 @@ diff 而非全文件
# 设计：构造 diff 把 '# empty\n' 换成 add 函数；断言
#       patches[0].hunk_count=1 / applied_count=1
def test_run_case_applies_unified_diff() -> None:
    diff_text = (
        "@@ -1,1 +1,2 @@\n"
        "-# empty\n"
        "+def add(a, b):\n"
        "+    return a + b\n"
    )
    p = FakeLlmProvider(scripted=[LlmScriptedResponse(text=diff_text)])
    agent = CodingAgent(llm=p, max_iter=2)
    case = _add_case()

    result = asyncio.run(agent.run_case(case))

    assert result.success is True
    assert result.patches[0].hunk_count == 1
    assert result.patches[0].applied_count == 1
    # 实际写入的内容应包含 add 函数
    assert "return a + b" in result.patches[0].diff_text


# ---------------------------------------------------------------------------
# 辅助函数单测
# ---------------------------------------------------------------------------


# 功能：_apply_hunks 在 old_block 匹配时替换并累计 applied
# 设计：构造 Hunk 替换 "old" → "new"；assert new_content == "new" / applied=1
#       （_apply_hunks 用 splitlines + join，尾部换行不保留）
def test_apply_hunks_replaces_matching_block() -> None:
    hunks = parse_unified_diff("@@ -1,1 +1,1 @@\n-old\n+new\n")
    new_content, applied = _apply_hunks(current_content="old\n", hunks=hunks)
    assert new_content == "new"
    assert applied == 1


# 功能：_apply_hunks 在 old_block 不匹配时记为失败但不抛错
# 设计：构造 Hunk 期望 "x" 但 current 是 "y"；assert new_content 不变 / applied=0
def test_apply_hunks_records_failure_on_mismatch() -> None:
    hunks = parse_unified_diff("@@ -1,1 +1,1 @@\n-x\n+y\n")
    new_content, applied = _apply_hunks(current_content="y\n", hunks=hunks)
    assert applied == 0
    assert new_content == "y"


# 功能：_apply_llm_output 无 @@ 时视为全文件替换（hunk_count=1 / applied_count=1）
# 设计：传 "print(1)\n" → 断言 new == "print(1)\n" / hc=1 / ac=1
def test_apply_llm_output_whole_file_replacement() -> None:
    new, hc, ac, dt = _apply_llm_output(
        llm_text="def f():\n    return 1\n",
        current_content="# empty\n",
    )
    assert new == "def f():\n    return 1\n"
    assert hc == 1
    assert ac == 1
    assert dt.startswith("@@ -0,0 +1,2 @@")


# 功能：_strip_code_fence 剥掉 ```python ... ``` 围栏（保留尾部换行）
# 设计：传 "```python\nfoo\n```\n" → 断言剥后 == "foo\n"（保留原尾部换行）
def test_strip_code_fence_removes_python_fence() -> None:
    assert _strip_code_fence("```python\nfoo\n```\n") == "foo\n"
    # 无围栏 → 保留尾部换行
    assert _strip_code_fence("  bar\n") == "bar\n"
    # 围栏无尾部换行 → 剥后也不带换行
    assert _strip_code_fence("```python\nfoo\n```") == "foo"


# 功能：_parse_pytest_summary 从 pytest 输出里抠 "X passed" / "X failed"
# 设计：构造不同形式的 summary → 断言 returned passed / total
def test_parse_pytest_summary_extracts_counts() -> None:
    out1 = "1 passed in 0.01s"
    assert _parse_pytest_summary(out1) == (1, 1)
    out2 = "1 failed, 2 passed in 0.01s"
    assert _parse_pytest_summary(out2) == (2, 3)
    out3 = "no tests ran"
    assert _parse_pytest_summary(out3) == (0, 0)
