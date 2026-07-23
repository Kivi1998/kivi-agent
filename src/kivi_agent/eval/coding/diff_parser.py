"""Unified diff hunk 解析（agent: package-eval-coding-v52）。

# diff_parser.py（agent: package-eval-coding-v52）
最小 unified diff 解析器，只关心 hunk 头（`@@ -a,b +c,d @@`）和内容。
- 不解析 file header（`--- /dev/null` 之类）—— LLM 输出的 patch 不一定规范
- 一律按行解析：@@ 行起新 hunk，+/-/空格 都进 hunk.lines
- 单 hunk 解析失败时记 "?" 作为 unknown 标记
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 匹配 unified diff hunk 头：@@ -1,2 +3,4 @@ （或省略计数：@@ -1 +3 @@）
_HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")


# 单个 hunk（agent: package-eval-coding-v52）
@dataclass
class Hunk:
    """unified diff 的一个 hunk 段。"""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    # 包含 +/-/空格 的原始行（不含 "diff"/"index"/"---"/"+++" 头部）
    lines: list[str] = field(default_factory=list)


# 把 unified diff 文本切成 hunk 列表（agent: package-eval-coding-v52）
def parse_unified_diff(diff_text: str) -> list[Hunk]:
    """解析 unified diff 文本，返回 hunk 列表。

    容错规则：
    - 空文本 → 空列表
    - 非 @@ 起始的行（"---"/"+++"/"diff"/"index"）一律跳过
    - @@ 行 = 新 hunk 起点；后续 +/-/空格 行追加到当前 hunk.lines
    - 任何非 +/-/空格/@@ 行结束当前 hunk
    """
    hunks: list[Hunk] = []
    if not diff_text:
        return hunks
    current: Hunk | None = None
    for raw in diff_text.splitlines():
        line = raw.rstrip("\n")
        m = _HUNK_HEADER_RE.match(line)
        if m:
            # 提交上一个 hunk，开始新的
            if current is not None:
                hunks.append(current)
            current = Hunk(
                old_start=int(m.group(1)),
                old_count=int(m.group(2) or 1),
                new_start=int(m.group(3)),
                new_count=int(m.group(4) or 1),
            )
            continue
        if current is None:
            # 没有遇到 @@ 头就跳过（diff / index / --- / +++ 等行）
            continue
        if not line:
            # 空行：可能 hunk 结束；保守起见继续累积
            current.lines.append(line)
            continue
        head = line[0]
        if head in ("+", "-", " "):
            current.lines.append(line)
        else:
            # 未知前缀 → 结束当前 hunk（防御性）
            hunks.append(current)
            current = None
    if current is not None:
        hunks.append(current)
    return hunks
