"""Demo 1：编程 Agent（agent: package-demo-v7）。

# demo1_coding.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / demo1 设计：
- 输入：fixtures/demo1_buggy_add.py（add 函数故意写错）
- 流程：CodingAgent 跑 T12 流程，迭代 3 次
- 期望：pytest 通过 + 3 指标（success / iteration_count / recovery_count）

可独立运行：`uv run python -m demos.demo1_coding`
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from kivi_agent.eval.coding.coding_agent import CodingAgent
from kivi_agent.eval.coding.models import CodingCase
from kivi_agent.eval.metrics import compute_all_coding_metrics
from tests._fakes.event_bus import FakeEventBus
from tests._fakes.llm import LlmScriptedResponse

from demos.base import DemoBase, DemoResult


# 修复 `a - b` bug 的脚本化 LLM 响应（agent: package-demo-v7）
_FIXED_ADD_RESPONSE = (
    "def add(a: int, b: int) -> int:\n"
    "    \"\"\"Return the sum of a and b.\"\"\"\n"
    "    return a + b\n"
)


# Demo 1：编程 Agent 用 CodingAgent 修复 add 函数（agent: package-demo-v7）
class Demo1Coding(DemoBase):
    """编程 Agent 演示：修复 fixtures/demo1_buggy_add.py 的 bug 并跑通 pytest。"""

    name = "demo1_coding"
    description = "编程 Agent：修复 add 函数的减法 bug 并跑通 pytest"

    # 跑 demo 业务逻辑（agent: package-demo-v7）
    async def run(self) -> DemoResult:
        # 1. 准备 fixture
        fixture = Path(__file__).parent / "fixtures" / "demo1_buggy_add.py"
        fixture_text = fixture.read_text(encoding="utf-8")

        # 2. 构造 CodingCase
        case = CodingCase(
            id="add-fix",
            task="Fix the `add` function so that add(a, b) == a + b.",
            test_file="tests/test_add.py",
            test_content=(
                "from mymod import add\n\n"
                "def test_add_basic():\n"
                "    assert add(1, 2) == 3\n"
                "def test_add_zero():\n"
                "    assert add(0, 5) == 5\n"
            ),
            initial_file="mymod.py",
            initial_content=fixture_text,
            expected_function="add",
            expected_tests_count=2,
            max_iter=3,
            difficulty="easy",
        )

        # 3. 注入 FakeLlmProvider：第一轮就给出正确答案（避免多轮浪费）
        from tests._fakes.llm import FakeLlmProvider

        llm = FakeLlmProvider(
            scripted=[LlmScriptedResponse(text=_FIXED_ADD_RESPONSE)],
            model="fake-fix-add",
        )

        # 4. 跑 CodingAgent
        agent = CodingAgent(llm=llm, max_iter=3, bus=FakeEventBus())
        result = await agent.run_case(case, sandbox=self.workdir)

        # 5. 算 3 个核心指标（task_completion_rate / iteration_count / self_recovery_rate）
        # compute_all_coding_metrics 期望 list[CodingEvalResult]
        report = compute_all_coding_metrics([result], dataset_name="demo1_coding")
        task_completion = report.metrics["task_completion_rate"]  # type: ignore[index]
        iter_metric = report.metrics["iteration_count"]  # type: ignore[index]
        recovery_metric = report.metrics["self_recovery_rate"]  # type: ignore[index]

        passed = result.success
        artifacts = {
            "iteration_count": result.iteration_count,
            "recovery_count": result.recovery_count,
            "final_passed": result.final_passed,
            "metrics": {
                "task_completion_rate": task_completion,
                "iteration_count": iter_metric,
                "self_recovery_rate": recovery_metric,
            },
        }
        summary = (
            f"iter={result.iteration_count} passed={result.final_passed} "
            f"recovery={result.recovery_count} "
            f"task_completion={task_completion.get('rate', 0):.2f}"  # type: ignore[union-attr]
        )
        return DemoResult(
            name=self.name,
            status="passed" if passed else "failed",
            summary=summary,
            duration_seconds=0.0,
            artifacts=artifacts,
        )


# 入口：`uv run python -m demos.demo1_coding`（agent: package-demo-v7）
def main() -> None:
    async def _go() -> DemoResult:
        async with Demo1Coding() as demo:
            return await demo.execute()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
