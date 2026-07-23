"""T12 diff_parser 单元测试（agent: package-eval-coding-v52）。

# test_diff_parser.py（agent: package-eval-coding-v52）
8+ 场景覆盖 unified diff hunk 解析的常见与边界情况。
"""
from __future__ import annotations

import pytest

from kivi_agent.eval.coding.diff_parser import Hunk, parse_unified_diff


# 功能：空文本 → 空列表
# 设计：parse_unified_diff("") → []
def test_parse_empty_text_returns_empty_list() -> None:
    assert parse_unified_diff("") == []


# 功能：单个 hunk 完整解析
# 设计：典型 3 行 diff（context + remove + add）→ 1 个 Hunk，lines 全收
def test_parse_single_hunk() -> None:
    diff = (
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    h = hunks[0]
    assert h.old_start == 1
    assert h.old_count == 2
    assert h.new_start == 1
    assert h.new_count == 2
    assert len(h.lines) == 3
    assert h.lines[0].startswith(" ")


# 功能：多 hunk 时按出现顺序入列表
# 设计：2 个 hunk 的 diff（+ header 行模拟 git 输出）→ 断言 hunks[0].old_start / hunks[1].old_start
def test_parse_multiple_hunks() -> None:
    diff = (
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
        "@@ -10,2 +10,2 @@\n"
        "-c\n"
        "+d\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 2
    assert hunks[0].old_start == 1
    assert hunks[1].old_start == 10
    # --- / +++ 是 header（不在 lines 里）
    assert all(not ln.startswith("---") for ln in hunks[0].lines)


# 功能：省略计数的 hunk 头 "@@ -1 +1 @@" 默认 count=1
# 设计：构造 @ -1 +1 @@ → 断言 old_count=1 / new_count=1
def test_parse_hunk_header_without_counts_defaults_to_one() -> None:
    diff = "@@ -1 +1 @@\n-x\n+y\n"
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].old_count == 1
    assert hunks[0].new_count == 1


# 功能：含 file header（diff --git / index / --- / +++）的 diff 仍能正确解析
# 设计：仿 git 输出的 diff 头 + 1 hunk → 断言只产生 1 hunk
def test_parse_ignores_git_file_headers() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 1234..5678 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].lines == ["-old", "+new"]


# 功能：context 行（" " 前缀）也收入 hunk.lines
# 设计：3 行 context（不变） + 1 行 - + 1 行 + → lines 长度 = 5
def test_parse_context_lines_preserved() -> None:
    diff = (
        "@@ -1,5 +1,5 @@\n"
        " a\n"
        " b\n"
        "-c\n"
        "+C\n"
        " d\n"
    )
    hunks = parse_unified_diff(diff)
    assert hunks[0].lines == [" a", " b", "-c", "+C", " d"]


# 功能：未知前缀（如普通文字）结束当前 hunk
# 设计：@@ 行 + 1 行合法 + 1 行 "garbage" + @@ 行 → 2 hunks（中间被截断）
def test_parse_unknown_prefix_ends_current_hunk() -> None:
    diff = (
        "@@ -1,1 +1,1 @@\n"
        "-x\n"
        "garbage line\n"
        "@@ -10,1 +10,1 @@\n"
        "-y\n"
        "+z\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 2
    assert hunks[0].lines == ["-x"]
    assert hunks[1].lines == ["-y", "+z"]


# 功能：Hunk dataclass 默认 lines 为空 list
# 设计：直接 Hunk(1,1,1,1) → 字段对得上 + lines == []
def test_hunk_dataclass_defaults() -> None:
    h = Hunk(old_start=1, old_count=1, new_start=1, new_count=1)
    assert h.lines == []
    assert (h.old_start, h.old_count, h.new_start, h.new_count) == (1, 1, 1, 1)


# 功能：trailing 新行（无 \n）也能正确切行
# 设计：@@ 头后无 \n 的 patch → 仍解析出 1 hunk
def test_parse_handles_missing_trailing_newline() -> None:
    diff = "@@ -1,1 +1,1 @@\n-x\n+y"  # 最后一行无 \n
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].lines == ["-x", "+y"]


# 功能：纯 file header（无 hunk）→ 空列表
# 设计：仅 ---/+++/diff 行 → 不产出任何 hunk
def test_parse_only_file_headers_returns_empty() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 1234..5678 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
    )
    assert parse_unified_diff(diff) == []
