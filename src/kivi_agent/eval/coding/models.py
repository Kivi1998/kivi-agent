"""T12 coding eval 数据类（agent: package-eval-coding-v52）。

# models.py（agent: package-eval-coding-v52）
字段对齐 plan §三 WT-H2：
- CodingCase：单 case 描述（task / test_file / initial_file / ...）
- CodingEvalResult：单 case 跑完结果（patches / test_runs / iteration_count / ...）
- PatchRecord：单轮 patch（iter / hunk_count / applied_count / diff_text）
- TestRunRecord：单轮 pytest（iter / passed / total / duration / output）

路径遍历保护：`test_file` / `initial_file` 等相对路径含 `..` 时直接拒绝。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# 单个 patch 记录（agent: package-eval-coding-v52）
class PatchRecord(BaseModel):
    """单轮 patch 记录。"""

    # 防止 pytest 误把本类当测试类收集（命名以 Patch 开头即可，但为安全显式标注）
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    iter: int
    hunk_count: int
    applied_count: int
    diff_text: str


# 单轮 pytest 记录（agent: package-eval-coding-v52）
class TestRunRecord(BaseModel):
    """单轮 pytest 记录。"""

    # 显式标注非测试类（类名以 Test 开头会被 pytest 默认尝试收集）
    __test__ = False
    model_config = ConfigDict(extra="ignore")

    iter: int
    passed: int
    total: int
    duration_seconds: float
    output: str = ""


# 单 case 描述（agent: package-eval-coding-v52）
class CodingCase(BaseModel):
    """T12 单 coding case 描述（与 plan §三 WT-H2 JSONL 字段对齐）。"""

    model_config = ConfigDict(extra="ignore")

    id: str
    task: str
    test_file: str
    test_content: str
    initial_file: str
    initial_content: str
    expected_function: str
    expected_tests_count: int = Field(default=1, ge=0)
    max_iter: int = Field(default=3, ge=1)
    difficulty: Literal["easy", "medium", "hard"] = "easy"

    # 路径遍历保护：test_file / initial_file 任何一段含 ".." 都拒绝
    @field_validator("test_file", "initial_file")
    @classmethod
    def _reject_traversal(cls, v: str) -> str:
        if ".." in Path(v).parts:
            raise ValueError(f"path traversal not allowed: {v}")
        return v


# 单 case coding eval 结果（agent: package-eval-coding-v52）
class CodingEvalResult(BaseModel):
    """T12 单 case 跑完结果。"""

    model_config = ConfigDict(extra="ignore")

    case_id: str
    started_at: str = Field(default_factory=_now_iso)
    finished_at: str | None = None
    patches: list[PatchRecord] = Field(default_factory=list)
    test_runs: list[TestRunRecord] = Field(default_factory=list)
    iteration_count: int = 0
    final_passed: int = 0
    success: bool = False
    recovery_count: int = 0


# JSONL 数据集容器（agent: package-eval-coding-v52）
class CodingDataset(BaseModel):
    """T12 coding 数据集（JSONL 一行一 case）。"""

    name: str
    version: str = "1"
    cases: list[CodingCase]

    # 从 JSONL 文件加载数据集
    @classmethod
    def load(cls, path: Path) -> CodingDataset:
        """从 JSONL 文件加载（每行一个 CodingCase）。"""
        # 路径遍历保护：路径段含 ".." 时直接拒绝
        if ".." in path.parts:
            raise ValueError(f"invalid dataset path: {path}")
        cases: list[CodingCase] = []
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data: dict[str, Any] = json.loads(line)
                    cases.append(CodingCase(**data))
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"line {line_no} invalid: {e}") from e
        return cls(name=path.stem, cases=cases)
