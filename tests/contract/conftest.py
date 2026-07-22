"""契约测试共享 pytest fixtures。

设计目标：
- 提供契约字面值的"单一来源"——所有契约测试从这里导入，不要硬编码
- 提供"协议期望"对象（dict/dataclass 形式），用于 A/B/C/D 未实现时仍可断言
- 不引入新的运行时依赖（仅 stdlib + 已有第三方包）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# ---- 契约字面值（来自 docs/contracts/v1.md） ---------------------------------

#: v1 §1 — 6 个冻结的业务 Tool 名称
V1_BUSINESS_TOOL_NAMES: tuple[str, ...] = (
    "web_search",
    "rag_query",
    "query_database",
    "echarts_render",
    "memory_save",
    "memory_recall",
)

#: v1 §1 — 5 个被弃的旧 Tool 名称（防止回潮）。
#:
#: 注意：``note_save`` **不**在此列表里。``note_save`` 是 Session Notes
#: （当前 run 内的短期笔记），与 ``memory_save``（跨 Session 长期记忆）
#: 是两个不同概念，详见用户核验 issue #4 与 v1 §1 注释。
#:
#: 历史背景：B 报告 §309/314/353 误把 ``note_save`` 当作 ``memory_save``
#: 的旧名，但实际它们指代不同功能。E 阶段经用户核验后修正。
V1_DEPRECATED_TOOL_NAMES: tuple[str, ...] = (
    "search_knowledge_base",  # B 报告误用
    "rag_query_rewrite",      # B 误为独立 Tool
    "db_query",               # C 报告旧名
    "chart_render",           # C 报告旧名
    "recall_memory",          # B 报告旧名
)

#: v1 §4 — Tool Schema 字段名（必须用 input_schema，不许用 params_schema）
V1_TOOL_SCHEMA_FIELD: str = "input_schema"
V1_TOOL_SCHEMA_FIELD_FORBIDDEN: str = "params_schema"

#: v1 当前 schema_version
V1_SCHEMA_VERSION: int = 1


# ---- "协议期望"对象 ----------------------------------------------------------

@dataclass(frozen=True)
class ExpectedRunContext:
    """v1 §2 冻结的 RunContext 字段期望。

    当 A 阶段尚未实现 RunContext 时，契约测试用这个对象做"协议对比"：
    一旦 A 实现完 RunContext，测试会 import 真实类并对比字段集一致。
    """

    schema_version: int = V1_SCHEMA_VERSION
    run_id: str = ""
    trace_id: str = ""
    user_id: str = ""
    session_id: str = ""
    datasource_id: str | None = None
    knowledge_base_id: str | None = None
    frontend_connection_id: str | None = None
    runtime_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpectedAgentProfile:
    """v1 §3 冻结的 AgentProfile 扩展字段期望（共 5 字段）。"""

    max_steps: int = 20
    permission_mode: str = "DEFAULT"
    result_schema: dict[str, Any] | None = None
    concurrency_group: str = "default"
    category: str = "other"


@pytest.fixture(scope="session")
def v1_business_tool_names() -> tuple[str, ...]:
    """v1 §1 冻结的 6 个业务 Tool 名。"""
    return V1_BUSINESS_TOOL_NAMES


@pytest.fixture(scope="session")
def v1_deprecated_tool_names() -> tuple[str, ...]:
    """v1 §1 弃用的 6 个旧 Tool 名（用于反向断言）。"""
    return V1_DEPRECATED_TOOL_NAMES


@pytest.fixture(scope="session")
def expected_run_context() -> ExpectedRunContext:
    """v1 §2 RunContext 协议期望（8 字段）。"""
    return ExpectedRunContext()


@pytest.fixture(scope="session")
def expected_agent_profile_ext() -> ExpectedAgentProfile:
    """v1 §3 AgentProfile 扩展字段协议期望（5 字段）。"""
    return ExpectedAgentProfile()


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """仓库根目录。"""
    # conftest.py 在 tests/contract/，上溯两级
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def analysis_report_dir(repo_root: Path) -> Path:
    """5 份只读分析报告所在目录。

    注：报告目前在 `integration/aigroup-eval` worktree，未合并到主仓。
    本测试为"协议级冒烟"，目录存在则扫描内容；不存在则跳过。
    """
    # 优先主仓内（如已合并）
    in_repo = repo_root / "docs" / "migration"
    if in_repo.exists():
        return in_repo
    # 回退到 worktree 路径（开发期）
    sibling_wt = repo_root.parent / "kivi-agent-wt-eval" / "docs" / "migration"
    if sibling_wt.exists():
        return sibling_wt
    # 找不到时返回主仓路径（让测试用 pytest.skip 标记）
    return in_repo
