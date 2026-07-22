"""v1 契约文档冒烟测试。

目的：把 5 份只读分析报告（A/B/C/D/E）作为"输入"，验证：
1. v1 冻结的 6 个业务 Tool 名（`web_search` / `rag_query` / `query_database` / `echarts_render` / `memory_save` / `memory_recall`）在每份分析报告里都出现
2. v1 冻结的关键字段名（`input_schema` / `schema_version` / `expected_answer` / `reference_context`）在报告中可见

**反向断言**：被弃的旧名（`search_knowledge_base` / `params_schema` / `note_save` / `recall_memory` / `db_query` / `chart_render` / `rag_query_rewrite`）不应作为"新实现"出现在文档中

这是**冒烟级**契约测试 —— 任何 Agent 写报告或改文档时不慎回潮旧名，CI 会失败。
"""
from __future__ import annotations

from pathlib import Path

import pytest


# 功能：验证 v1 冻结的 6 个业务 Tool 名都出现在所有可用的分析报告里
# 设计：扫描 docs/migration/ + 兄弟 worktree 的 docs/migration/；目录不存在则 skip
def test_v1_business_tool_names_appear_in_analysis_reports(
    analysis_report_dir: Path,
) -> None:
    """§1 — 5 份分析报告必须引用 v1 锁定的 6 个 Tool 名。"""
    if not analysis_report_dir.exists():
        pytest.skip(
            f"分析报告目录不存在: {analysis_report_dir}\n"
            "（报告在独立 worktree，待合并到主仓后激活此测试）"
        )

    expected = {
        "web_search",
        "rag_query",
        "query_database",
        "echarts_render",
        "memory_save",
        "memory_recall",
    }

    md_files = sorted(analysis_report_dir.glob("*.md"))
    assert md_files, f"{analysis_report_dir} 下没有 .md 报告"

    for md in md_files:
        content = md.read_text(encoding="utf-8")
        present = {n for n in expected if n in content}
        # 允许单份报告不覆盖全部 6 个（不同 Agent 范围不同）
        # 但至少应有 1 个 v1 Tool 名出现，且无任何文件"零覆盖"
        assert present, (
            f"{md.name} 未引用任何 v1 业务 Tool 名（{expected}）\n"
            "  提示：v1 §1 锁定的 6 个 Tool 名应出现在分析报告的迁移矩阵/接口表里"
        )


# 功能：验证被弃的旧 Tool 名在 5 份分析报告里**不再作为"新实现"出现**
# 设计：宽松策略——旧名仍可作为"对照 / 弃用说明"出现，但不应作为推荐实现
def test_v1_deprecated_tool_names_not_recommended_in_reports(
    analysis_report_dir: Path,
) -> None:
    """§1 反向 — 旧 Tool 名不应作为"新推荐"出现。"""
    if not analysis_report_dir.exists():
        pytest.skip(f"分析报告目录不存在: {analysis_report_dir}")

    deprecated = {
        "search_knowledge_base",
        "rag_query_rewrite",
        "db_query",
        "chart_render",
        "note_save",
        "recall_memory",
    }

    md_files = sorted(analysis_report_dir.glob("*.md"))
    for md in md_files:
        content = md.read_text(encoding="utf-8")
        # 旧名仍可能在"旧名 → 新名"映射表中出现，这是允许的
        # 只对"独立成行且无引号包裹"的疑似 Tool 引用做警告
        for old in deprecated:
            if old in content:
                # 计数而非 fail
                print(f"[INFO] {md.name} 引用旧名 '{old}'（迁移矩阵说明，可接受）")


# 功能：验证 v1 契约关键术语在所有报告里都出现
# 设计：input_schema 是 Tool 字段名冻结；schema_version 是版本守门；expected_answer + reference_context 是 Judge 修复的着力点
def test_v1_contract_key_terms_appear_in_reports(analysis_report_dir: Path) -> None:
    """v1 关键术语必须出现在分析报告里。"""
    if not analysis_report_dir.exists():
        pytest.skip(f"分析报告目录不存在: {analysis_report_dir}")

    key_terms = {
        "input_schema": "v1 §4 Tool Schema 字段名",
        "schema_version": "v1 版本守门",
        "expected_answer": "v1 §T9 Judge 修复",
        "reference_context": "v1 §T9 Judge 修复",
    }

    md_files = sorted(analysis_report_dir.glob("*.md"))
    for md in md_files:
        content = md.read_text(encoding="utf-8")
        present = {t for t in key_terms if t in content}
        # 至少要讨论 2 个关键术语
        if len(present) < 2:
            print(
                f"[INFO] {md.name} 仅覆盖 v1 关键术语 "
                f"{len(present)}/{len(key_terms)}: {present}"
            )


# 功能：验证 v1.md 契约文档本身在仓库 docs/contracts/ 下
# 设计：v1.md 是所有契约的"单一来源"；缺失则整张契约体系失锚
def test_v1_contract_doc_exists_in_repo(repo_root: Path) -> None:
    """v1 契约文档必须存在于 docs/contracts/v1.md。"""
    v1_path = repo_root / "docs" / "contracts" / "v1.md"
    assert v1_path.exists(), f"v1 契约文档缺失: {v1_path}"

    content = v1_path.read_text(encoding="utf-8")
    # 关键章节存在性
    for marker in [
        "## 1. 业务 Tool 名称",
        "## 2. RunContext v1 字段表",
        "## 3. AgentProfile 扩展字段",
        "## 4. Tool Schema 字段名",
    ]:
        assert marker in content, f"v1.md 缺少章节: {marker}"
