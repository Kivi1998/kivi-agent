"""T12 CodingAgent 集成测试（agent: package-eval-coding-v52）。

# test_coding_run.py（agent: package-eval-coding-v52）
3+ 端到端 case：
1. 全 happy path：6 case 全部 iter=1 通过
2. 部分失败 + 自愈：4 case 一次过 + 2 case 一次失败一次过
3. 全部 max_iter 失败：3 case 全 broken，iter 用完仍不通过
4. 8 指标 + MetricsReport 端到端（基于 happy path 结果）
"""
from __future__ import annotations

import asyncio

from kivi_agent.eval.coding.coding_agent import CodingAgent
from kivi_agent.eval.coding.models import CodingCase, CodingDataset
from kivi_agent.eval.metrics import compute_all_coding_metrics
from tests._fakes.event_bus import FakeEventBus
from tests._fakes.llm import FakeLlmProvider, LlmScriptedResponse


# 工厂：构造 add / fib / reverse / parse / dedup / sort 6 case（agent: package-eval-coding-v52）
def _make_dataset() -> CodingDataset:
    """构造 6 case 演示数据集。"""
    cases_data = [
        # 1. add
        {
            "id": "add", "task": "add(a, b)", "max_iter": 3,
            "test_file": "tests/test_add.py",
            "test_content": "from mymod import add\n\n"
            "def test_add():\n    assert add(1, 2) == 3\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "add", "expected_tests_count": 1, "difficulty": "easy",
        },
        # 2. fibonacci
        {
            "id": "fib", "task": "fib(n) returns nth Fibonacci", "max_iter": 3,
            "test_file": "tests/test_fib.py",
            "test_content": "from mymod import fib\n\n"
            "def test_fib():\n    assert fib(5) == 5\n    assert fib(0) == 0\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "fib", "expected_tests_count": 1, "difficulty": "medium",
        },
        # 3. reverse_string
        {
            "id": "rev", "task": "reverse_string(s) returns reversed", "max_iter": 3,
            "test_file": "tests/test_rev.py",
            "test_content": "from mymod import reverse_string\n\n"
            "def test_rev():\n    assert reverse_string('abc') == 'cba'\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "reverse_string", "expected_tests_count": 1, "difficulty": "easy",
        },
        # 4. parse_url
        {
            "id": "url", "task": "parse_url(s) returns dict with 'host' key", "max_iter": 3,
            "test_file": "tests/test_url.py",
            "test_content": "from mymod import parse_url\n\n"
            "def test_url():\n    r = parse_url('http://example.com/path')\n"
            "    assert r['host'] == 'example.com'\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "parse_url", "expected_tests_count": 1, "difficulty": "medium",
        },
        # 5. dedup
        {
            "id": "dedup", "task": "dedup(lst) removes duplicates preserving order", "max_iter": 3,
            "test_file": "tests/test_dedup.py",
            "test_content": "from mymod import dedup\n\n"
            "def test_dedup():\n    assert dedup([1, 2, 1, 3]) == [1, 2, 3]\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "dedup", "expected_tests_count": 1, "difficulty": "easy",
        },
        # 6. sort_dict
        {
            "id": "sort", "task": "sort_dict(d) returns dict sorted by value desc", "max_iter": 3,
            "test_file": "tests/test_sort.py",
            "test_content": "from mymod import sort_dict\n\n"
            "def test_sort():\n    r = sort_dict({'a': 3, 'b': 1})\n"
            "    assert list(r.values()) == [3, 1]\n",
            "initial_file": "mymod.py", "initial_content": "# empty\n",
            "expected_function": "sort_dict", "expected_tests_count": 1, "difficulty": "medium",
        },
    ]
    cases = [CodingCase(**c) for c in cases_data]  # type: ignore[arg-type]
    return CodingDataset(name="demo-coding-6", cases=cases)


# 功能：happy path — 6 case 全 iter=1 通过
# 设计：6 LLM scripted 各返回对应函数 → 全部 success=True / iter=1
def test_coding_run_all_pass_iter_one() -> None:
    bus = FakeEventBus()
    cases = _make_dataset().cases
    # 每个 case 一条 scripted 响应
    responses = [
        LlmScriptedResponse(text="def add(a, b):\n    return a + b\n"),
        LlmScriptedResponse(text="def fib(n):\n    a, b = 0, 1\n    for _ in range(n): a, b = b, a + b\n    return a\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s[::-1]\n"),
        LlmScriptedResponse(
            text="def parse_url(s):\n    from urllib.parse import urlparse\n"
            "    p = urlparse(s)\n    return {'host': p.netloc}\n"
        ),
        LlmScriptedResponse(text="def dedup(lst):\n    seen = set()\n    out = []\n    [seen.add(x) or out.append(x) for x in lst if x not in seen]\n    return out\n"),
        LlmScriptedResponse(text="def sort_dict(d):\n    return dict(sorted(d.items(), key=lambda x: -x[1]))\n"),
    ]
    p = FakeLlmProvider(scripted=responses)
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)

    results = asyncio.run(_run_all(agent, cases))

    assert len(results) == 6
    assert all(r.success for r in results), f"failed: {[r.case_id for r in results if not r.success]}"
    assert all(r.iteration_count == 1 for r in results)
    assert all(r.final_passed == r.test_runs[0].total for r in results)


# 功能：部分失败 + 自愈 — 4 case 一次过 + 2 case fail→pass
# 设计：前 4 case 给正确实现；后 2 case 给 broken→fixed 两条响应；
#       断言 6 case 全 success / recovery_count=2
def test_coding_run_partial_fail_with_recovery() -> None:
    bus = FakeEventBus()
    cases = _make_dataset().cases
    responses = [
        LlmScriptedResponse(text="def add(a, b):\n    return a + b\n"),
        LlmScriptedResponse(text="def fib(n):\n    a, b = 0, 1\n    for _ in range(n): a, b = b, a + b\n    return a\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s[::-1]\n"),
        LlmScriptedResponse(
            text="def parse_url(s):\n    from urllib.parse import urlparse\n"
            "    p = urlparse(s)\n    return {'host': p.netloc}\n"
        ),
        # case5: broken then fixed（broken 真坏：return None；fixed 正确）
        LlmScriptedResponse(text="def dedup(lst):\n    return None\n"),
        LlmScriptedResponse(text="def dedup(lst):\n    seen, out = set(), []\n    [seen.add(x) or out.append(x) for x in lst if x not in seen]\n    return out\n"),
        # case6: broken then fixed（broken 真坏：升序；fixed 是降序）
        LlmScriptedResponse(text="def sort_dict(d):\n    return dict(sorted(d.items(), key=lambda x: x[1]))\n"),
        LlmScriptedResponse(text="def sort_dict(d):\n    return dict(sorted(d.items(), key=lambda x: -x[1]))\n"),
    ]
    p = FakeLlmProvider(scripted=responses)
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)

    results = asyncio.run(_run_all(agent, cases))

    assert len(results) == 6
    # 全部最终成功
    assert all(r.success for r in results)
    # 2 个 case 走了自愈路径
    recoveries = [r for r in results if r.recovery_count > 0]
    assert len(recoveries) == 2


# 功能：max_iter 用完仍失败 — 3 case 全 broken，iter 跑完不通过
# 设计：3 LLM 全 broken → success=False / iter=3 / final_passed=0
def test_coding_run_exhausts_max_iter() -> None:
    bus = FakeEventBus()
    cases = _make_dataset().cases[:3]
    responses = [
        LlmScriptedResponse(text="def add(a, b):\n    return a - b\n"),
        LlmScriptedResponse(text="def add(a, b):\n    return 0\n"),
        LlmScriptedResponse(text="def add(a, b):\n    raise Exception()\n"),
        LlmScriptedResponse(text="def fib(n):\n    return 0\n"),
        LlmScriptedResponse(text="def fib(n):\n    return 1\n"),
        LlmScriptedResponse(text="def fib(n):\n    return -1\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s + s\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s[::2]\n"),
    ]
    p = FakeLlmProvider(scripted=responses)
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)

    results = asyncio.run(_run_all(agent, cases))

    assert len(results) == 3
    assert all(not r.success for r in results)
    assert all(r.iteration_count == 3 for r in results)


# 功能：8 指标端到端 — happy path 跑完 + compute_all_coding_metrics 输出 8 指标
# 设计：先跑 6 case → 把 results 喂进 compute_all_coding_metrics → 验证 metrics dict 含 8 key
def test_coding_run_metrics_e2e() -> None:
    bus = FakeEventBus()
    cases = _make_dataset().cases
    responses = [
        LlmScriptedResponse(text="def add(a, b):\n    return a + b\n"),
        LlmScriptedResponse(text="def fib(n):\n    a, b = 0, 1\n    for _ in range(n): a, b = b, a + b\n    return a\n"),
        LlmScriptedResponse(text="def reverse_string(s):\n    return s[::-1]\n"),
        LlmScriptedResponse(
            text="def parse_url(s):\n    from urllib.parse import urlparse\n"
            "    p = urlparse(s)\n    return {'host': p.netloc}\n"
        ),
        LlmScriptedResponse(text="def dedup(lst):\n    seen, out = set(), []\n    [seen.add(x) or out.append(x) for x in lst if x not in seen]\n    return out\n"),
        LlmScriptedResponse(text="def sort_dict(d):\n    return dict(sorted(d.items(), key=lambda x: -x[1]))\n"),
    ]
    p = FakeLlmProvider(scripted=responses)
    agent = CodingAgent(llm=p, max_iter=3, bus=bus)
    results = asyncio.run(_run_all(agent, cases))

    report = compute_all_coding_metrics(results, dataset_name="demo-coding-6")

    assert report.case_count == 6
    assert set(report.metrics.keys()) == {
        "task_completion_rate",
        "tests_passed_rate",
        "patch_quality",
        "iteration_count",
        "time_to_first_pass",
        "self_recovery_rate",
        "compile_success_rate",
        "test_growth_rate",
    }
    # happy path：6/6 完成 / tests 100% / patch 100%
    assert report.metrics["task_completion_rate"]["rate"] == 1.0
    assert report.metrics["tests_passed_rate"]["rate"] == 1.0
    assert report.metrics["patch_quality"]["rate"] == 1.0
    assert report.metrics["self_recovery_rate"]["rate"] == 0.0
    assert report.metrics["compile_success_rate"]["rate"] == 1.0


# ---------------------------------------------------------------------------
# 辅助：顺序跑全部 case（agent: package-eval-coding-v52）
# ---------------------------------------------------------------------------


# 顺序跑 dataset 全部 case（不并发，便于 deterministic scripted 响应）
async def _run_all(agent: CodingAgent, cases: list[CodingCase]) -> list:
    out = []
    for c in cases:
        r = await agent.run_case(c)
        out.append(r)
    return out
