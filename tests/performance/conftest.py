"""性能基线公共 fixture（agent: package-stage8-baselines-v7）。

# conftest.py（performance / agent: package-stage8-baselines-v7）
- `repo_root` fixture：返回项目根目录（test_benchmarks.py 用它写 reports/）
- pytest 自动发现 tests/performance/conftest.py；不与 tests/conftest.py 冲突
"""
from __future__ import annotations

from pathlib import Path

import pytest


# 功能：返回项目根目录（test_benchmarks.py 用它写 reports/）
# 设计：__file__ 在 tests/performance/conftest.py → 上两级目录即仓库根
@pytest.fixture
def repo_root() -> Path:
    """返回仓库根目录绝对路径。"""
    return Path(__file__).resolve().parent.parent.parent
