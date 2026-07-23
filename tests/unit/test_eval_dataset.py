"""EvalCase / EvalDataset 单元测试（agent: package-eval-dataset-v51）。

覆盖 4 个核心场景：
1. 加载有效 JSONL → 成功解析 + 字段完整
2. 加载无效 JSON → ValueError（含行号）
3. 按 tag 过滤
4. 路径遍历保护（".." 段 → 拒绝）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kivi_agent.eval.dataset import EvalDataset


# 写一个有效 case 到 JSONL 临时文件（测试用 helper）
def _write_cases(path: Path, cases: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# 功能：验证加载有效 JSONL 后 EvalCase 字段完整
# 设计：写 2 个 case（覆盖 easy/medium 不同 difficulty）→ 解析后逐字段断言，
#       验证默认 factory（tags / expected_tools / expected_sources）也能工作
def test_load_valid_jsonl_parses_all_fields(tmp_path: Path) -> None:
    p = tmp_path / "dataset.jsonl"
    _write_cases(p, [
        {
            "id": "c1",
            "goal": "查一下公司年假政策",
            "expected_route": "rag",
            "expected_tools": ["rag_query"],
            "expected_sources": ["kb-001", "kb-002"],
            "expected_answer": "年假 10 天",
            "difficulty": "easy",
            "tags": ["rag", "policy"],
        },
        {
            "id": "c2",
            "goal": "统计 7 月订单数",
            "expected_route": "database",
            "tags": ["database"],
        },
    ])

    ds = EvalDataset.load(p)

    assert ds.name == "dataset"
    assert len(ds.cases) == 2
    c1 = ds.cases[0]
    assert c1.id == "c1"
    assert c1.expected_route == "rag"
    assert c1.expected_tools == ["rag_query"]
    assert c1.expected_sources == ["kb-001", "kb-002"]
    assert c1.expected_answer == "年假 10 天"
    assert c1.difficulty == "easy"
    assert c1.tags == ["rag", "policy"]
    # c2 验证默认值（difficulty 兜底 medium + 空 list 兜底）
    c2 = ds.cases[1]
    assert c2.difficulty == "medium"
    assert c2.expected_tools == []
    assert c2.expected_sources == []


# 功能：验证加载含无效 JSON 行时抛 ValueError（带行号）
# 设计：在 JSONL 第 2 行放非法 JSON（"{" 单独行）→ 断言错误消息含行号
#       + ValueError 类型；行号必须来自 enumerate(start=1)
def test_load_invalid_json_raises_value_error_with_line_number(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        # 第 1 行有效；第 2 行非法 JSON
        f.write(json.dumps({"id": "ok", "goal": "x"}) + "\n")
        f.write("{not valid json}\n")

    with pytest.raises(ValueError) as exc:
        EvalDataset.load(p)
    msg = str(exc.value)
    assert "line 2" in msg, f"expected 'line 2' in error, got: {msg}"


# 功能：验证按 tag 过滤只保留含该 tag 的 case
# 设计：3 个 case 分别带 / 不带 "rag" tag → filter("rag") 留下 2 个，
#       新 EvalDataset.name 带 "_tag_rag" 后缀（与实现一致）
def test_filter_by_tag_returns_matching_cases(tmp_path: Path) -> None:
    p = tmp_path / "ds.jsonl"
    _write_cases(p, [
        {"id": "a", "goal": "g1", "tags": ["rag"]},
        {"id": "b", "goal": "g2", "tags": ["database"]},
        {"id": "c", "goal": "g3", "tags": ["rag", "policy"]},
    ])

    ds = EvalDataset.load(p)
    filtered = ds.filter("rag")

    assert filtered.name == "ds_tag_rag"
    assert [c.id for c in filtered.cases] == ["a", "c"]


# 功能：验证加载含 ".." 路径段时直接拒绝（路径遍历保护）
# 设计：构造 Path("foo/../bar.jsonl") → 断言抛 ValueError，
#       错误消息含原始路径字符串便于排错
def test_load_rejects_path_traversal_double_dot() -> None:
    bad_path = Path("some/../malicious.jsonl")
    assert ".." in bad_path.parts  # 预校验测试设计本身有效

    with pytest.raises(ValueError) as exc:
        EvalDataset.load(bad_path)
    assert "invalid dataset path" in str(exc.value)
