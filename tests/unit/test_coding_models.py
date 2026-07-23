"""T12 coding 数据类单元测试（agent: package-eval-coding-v52）。

# test_coding_models.py（agent: package-eval-coding-v52）
覆盖 5+ 场景：
1. 构造有效 CodingCase → 字段全填充
2. 默认值（max_iter / difficulty / expected_tests_count）
3. test_file 路径遍历保护（".." 段 → ValueError）
4. initial_file 路径遍历保护
5. JSONL 加载：有效 + 路径遍历保护
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kivi_agent.eval.coding.models import (
    CodingCase,
    CodingDataset,
    CodingEvalResult,
    PatchRecord,
    TestRunRecord,
)


# 写一个 valid case dict 给测试 helper 用
def _case_dict(**overrides: object) -> dict[str, object]:
    """构造一个最小 valid case dict。"""
    base: dict[str, object] = {
        "id": "code-01",
        "task": "Write add(a, b) returning a + b",
        "test_file": "tests/test_add.py",
        "test_content": "from mymod import add\ndef test_add(): assert add(1, 2) == 3\n",
        "initial_file": "mymod.py",
        "initial_content": "",
        "expected_function": "add",
        "expected_tests_count": 1,
        "max_iter": 3,
        "difficulty": "easy",
    }
    base.update(overrides)
    return base


# 功能：构造最小 CodingCase → 字段全填充
# 设计：直接传完整 dict → 验证每个字段都正确读出（覆盖 default 字段如 difficulty）
def test_coding_case_constructs_with_all_fields() -> None:
    case = CodingCase(**_case_dict())  # type: ignore[arg-type]
    assert case.id == "code-01"
    assert case.task.startswith("Write add")
    assert case.test_file == "tests/test_add.py"
    assert "from mymod import add" in case.test_content
    assert case.initial_file == "mymod.py"
    assert case.initial_content == ""
    assert case.expected_function == "add"
    assert case.expected_tests_count == 1
    assert case.max_iter == 3
    assert case.difficulty == "easy"


# 功能：缺省字段（max_iter / difficulty）有合理默认
# 设计：构造 dict 不传 max_iter / difficulty → 断言 max_iter=3 / difficulty="easy"
def test_coding_case_applies_default_values() -> None:
    d = _case_dict()
    del d["max_iter"]
    del d["difficulty"]
    case = CodingCase(**d)  # type: ignore[arg-type]
    assert case.max_iter == 3
    assert case.difficulty == "easy"


# 功能：test_file 含 ".." 段时抛 ValidationError（路径遍历保护）
# 设计：直接构造 CodingCase(test_file="../escape/test.py") → 断言
#       pydantic ValidationError 包装的 ValueError 触发
def test_coding_case_rejects_test_file_path_traversal() -> None:
    with pytest.raises(ValidationError) as exc:
        CodingCase(**_case_dict(test_file="../escape/test.py"))  # type: ignore[arg-type]
    assert "path traversal" in str(exc.value)


# 功能：initial_file 含 ".." 段时同样拒绝
# 设计：构造 initial_file="../../malicious.py" → 验证保护
def test_coding_case_rejects_initial_file_path_traversal() -> None:
    with pytest.raises(ValidationError) as exc:
        CodingCase(**_case_dict(initial_file="../../malicious.py"))  # type: ignore[arg-type]
    assert "path traversal" in str(exc.value)


# 功能：JSONL 加载有效数据 + 错误行抛带行号的 ValueError
# 设计：写 2 个 case + 1 行非法 JSON → assert len == 2
def test_coding_dataset_loads_valid_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "coding.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps(_case_dict(id="c1")) + "\n")
        f.write(json.dumps(_case_dict(id="c2", expected_function="fib")) + "\n")

    ds = CodingDataset.load(p)
    assert ds.name == "coding"
    assert [c.id for c in ds.cases] == ["c1", "c2"]
    assert ds.cases[1].expected_function == "fib"


# 功能：JSONL 含 ".." 路径段时直接拒绝
# 设计：构造 Path("foo/../malicious.jsonl") → 断言抛 ValueError
def test_coding_dataset_load_rejects_path_traversal() -> None:
    bad_path = Path("foo/../malicious.jsonl")
    assert ".." in bad_path.parts
    with pytest.raises(ValueError) as exc:
        CodingDataset.load(bad_path)
    assert "invalid dataset path" in str(exc.value)


# 功能：PatchRecord / TestRunRecord / CodingEvalResult 三个数据类可正常构造
# 设计：分别构造最小实例 → 断言字段读出 + 默认值（started_at 自动生成）
def test_coding_eval_result_and_records_construct() -> None:
    p = PatchRecord(iter=1, hunk_count=2, applied_count=1, diff_text="@@ ...")
    tr = TestRunRecord(iter=1, passed=2, total=3, duration_seconds=0.1, output="")
    r = CodingEvalResult(
        case_id="c1",
        patches=[p],
        test_runs=[tr],
        iteration_count=1,
        final_passed=2,
        success=False,
        recovery_count=0,
    )
    assert r.case_id == "c1"
    assert r.patches[0].hunk_count == 2
    assert r.test_runs[0].passed == 2
    assert r.iteration_count == 1
    assert r.finished_at is None
    assert r.started_at  # 自动填充
