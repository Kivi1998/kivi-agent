"""memory_save + memory_recall 业务 Tool 测试（agent: package-c-v1）。

覆盖：
- Tool 协议：name / category / input_schema 正确（save=write, recall=read）
- save 写入 frontmatter 4 字段：memory_type / importance / status / created_at
- save 落盘：文件可读 + 解析回 LongTermMemoryEntry
- recall substring 匹配 + importance 加权排序
- save + recall 端到端 round-trip
- top_k 限制生效
- 参数校验：缺 content / 缺 query 返回 schema_error
- importance 1-10 边界
- 默认 memory_type=fact / 默认 importance=5 / 默认 top_k=5
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from kivi_agent.core.business.memory_recall import MemoryRecallTool
from kivi_agent.core.business.memory_save import MemorySaveTool
from kivi_agent.core.tools.base import ToolResult


# 每个测试用独立 tmp 目录，避免相互污染
@pytest.fixture
def mem_root(tmp_path: Path) -> Path:
    return tmp_path / "memory"


# === T6 Part 1: memory_save Tool 协议 ===

# 功能：memory_save Tool 协议字段正确
def test_memory_save_tool_metadata() -> None:
    tool = MemorySaveTool()
    assert tool.name == "memory_save"
    assert tool.category == "write"  # 写入是写操作
    assert tool.input_schema["required"] == ["content"]
    # importance 1-10
    imp_schema = tool.input_schema["properties"]["importance"]
    assert imp_schema["minimum"] == 1
    assert imp_schema["maximum"] == 10
    assert imp_schema["default"] == 5
    # memory_type 包含 7 种
    mt_enum = tool.input_schema["properties"]["memory_type"]["enum"]
    assert set(mt_enum) == {"fact", "preference", "decision", "instruction", "correction", "summary", "reference"}


# === T6 Part 2: memory_recall Tool 协议 ===

# 功能：memory_recall Tool 协议字段正确
def test_memory_recall_tool_metadata() -> None:
    tool = MemoryRecallTool()
    assert tool.name == "memory_recall"
    assert tool.category == "read"
    assert tool.input_schema["required"] == ["query"]
    # top_k 1-100
    top_k_schema = tool.input_schema["properties"]["top_k"]
    assert top_k_schema["minimum"] == 1
    assert top_k_schema["maximum"] == 100
    assert top_k_schema["default"] == 5


# === T6 Part 3: memory_save 写入行为 ===

# 功能：save 写入磁盘 + 4 字段 frontmatter 正确
async def test_memory_save_writes_to_disk(mem_root: Path) -> None:
    tool = MemorySaveTool(root=mem_root)
    result = await tool.invoke({"content": "用户偏好简洁回复", "memory_type": "preference", "importance": 8})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["memory_type"] == "preference"
    assert data["importance"] == 8
    assert data["status"] == "active"
    assert "created_at" in data
    assert "memory_id" in data
    # 文件实际落盘
    saved_path = Path(data["path"])
    assert saved_path.exists()
    assert saved_path.parent == mem_root
    # 文件内容含 frontmatter
    text = saved_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "memory_type: preference" in text
    assert "importance: 8" in text
    assert "status: active" in text
    assert "用户偏好简洁回复" in text


# 功能：save 默认值：memory_type=fact, importance=5
async def test_memory_save_default_values(mem_root: Path) -> None:
    tool = MemorySaveTool(root=mem_root)
    result = await tool.invoke({"content": "默认测试"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["memory_type"] == "fact"
    assert data["importance"] == 5
    assert data["status"] == "active"


# 功能：save 缺 content 返回 schema_error
async def test_memory_save_missing_content(mem_root: Path) -> None:
    tool = MemorySaveTool(root=mem_root)
    result = await tool.invoke({})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：importance 越界返回 schema_error
async def test_memory_save_importance_out_of_range(mem_root: Path) -> None:
    tool = MemorySaveTool(root=mem_root)
    r_low = await tool.invoke({"content": "x", "importance": 0})
    assert r_low.is_error and r_low.error_type == "schema_error"
    r_high = await tool.invoke({"content": "x", "importance": 11})
    assert r_high.is_error and r_high.error_type == "schema_error"


# 功能：memory_type 不在枚举返回 schema_error
async def test_memory_save_invalid_memory_type(mem_root: Path) -> None:
    tool = MemorySaveTool(root=mem_root)
    result = await tool.invoke({"content": "x", "memory_type": "unknown"})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：save 后 recall 能召回（end-to-end round-trip）
async def test_memory_save_recall_round_trip(mem_root: Path) -> None:
    save_tool = MemorySaveTool(root=mem_root)
    recall_tool = MemoryRecallTool(root=mem_root)
    # 写入 3 条记忆
    await save_tool.invoke({"content": "RAG 系统由 query rewrite + retrieval + answer generation 组成", "memory_type": "fact", "importance": 7})
    await save_tool.invoke({"content": "用户偏好 Python 异步编程", "memory_type": "preference", "importance": 9})
    await save_tool.invoke({"content": "下次演示用 ECharts 5.x 渲染图表", "memory_type": "decision", "importance": 6})
    # recall 关键词 "RAG"
    result = await recall_tool.invoke({"query": "RAG"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["count"] >= 1
    # 找到 RAG 那条
    contents = [m["content"] for m in data["memories"]]
    assert any("RAG" in c for c in contents)


# 功能：recall substring 匹配 + importance 排序
async def test_memory_recall_importance_weighted_ranking(mem_root: Path) -> None:
    save_tool = MemorySaveTool(root=mem_root)
    recall_tool = MemoryRecallTool(root=mem_root)
    # 写入：低 importance 1 条 + 高 importance 1 条（都用 "Python" 关键词）
    await save_tool.invoke({"content": "Python 入门教程", "importance": 3})
    await save_tool.invoke({"content": "Python 高级异步编程", "importance": 9})
    result = await recall_tool.invoke({"query": "Python"})
    data = json.loads(result.content)
    # 应该返回 2 条
    assert data["count"] == 2
    # importance=9 的应排在前
    assert data["memories"][0]["importance"] == 9
    assert data["memories"][1]["importance"] == 3


# 功能：recall top_k 限制生效
async def test_memory_recall_top_k_limit(mem_root: Path) -> None:
    save_tool = MemorySaveTool(root=mem_root)
    recall_tool = MemoryRecallTool(root=mem_root)
    # 写入 5 条都含 "test"
    for i in range(5):
        await save_tool.invoke({"content": f"test content {i}", "importance": 5})
    # recall top_k=3
    result = await recall_tool.invoke({"query": "test", "top_k": 3})
    data = json.loads(result.content)
    assert data["count"] == 3
    assert data["top_k"] == 3


# 功能：recall 不匹配时返回空
async def test_memory_recall_no_match(mem_root: Path) -> None:
    save_tool = MemorySaveTool(root=mem_root)
    recall_tool = MemoryRecallTool(root=mem_root)
    await save_tool.invoke({"content": "Python 教程"})
    result = await recall_tool.invoke({"query": "不存在的关键词xyz"})
    data = json.loads(result.content)
    assert data["count"] == 0


# 功能：recall 缺 query 返回 schema_error
async def test_memory_recall_missing_query(mem_root: Path) -> None:
    tool = MemoryRecallTool(root=mem_root)
    result = await tool.invoke({})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：recall top_k 越界返回 schema_error
async def test_memory_recall_top_k_out_of_range(mem_root: Path) -> None:
    tool = MemoryRecallTool(root=mem_root)
    r0 = await tool.invoke({"query": "x", "top_k": 0})
    assert r0.is_error and r0.error_type == "schema_error"
    r101 = await tool.invoke({"query": "x", "top_k": 101})
    assert r101.is_error and r101.error_type == "schema_error"


# 功能：Pydantic 直接校验
def test_memory_save_params_validation() -> None:
    from kivi_agent.core.business.memory_save import MemorySaveParams

    p = MemorySaveParams.model_validate({"content": "x"})
    assert p.memory_type == "fact"  # 默认
    assert p.importance == 5  # 默认
    p2 = MemorySaveParams.model_validate({"content": "x", "memory_type": "decision", "importance": 10})
    assert p2.memory_type == "decision"
    with pytest.raises(ValidationError):
        MemorySaveParams.model_validate({})


def test_memory_recall_params_validation() -> None:
    from kivi_agent.core.business.memory_recall import MemoryRecallParams

    p = MemoryRecallParams.model_validate({"query": "x"})
    assert p.top_k == 5  # 默认
    with pytest.raises(ValidationError):
        MemoryRecallParams.model_validate({})


# 功能：同一 backend 跨 save/recall 共享（不破坏 A 阶段 MemoryStore）
async def test_memory_save_uses_dedicated_directory(mem_root: Path) -> None:
    """memory_save 写到独立子目录，不污染 A 阶段 MemoryStore 的 4 字段文件"""
    save_tool = MemorySaveTool(root=mem_root)
    await save_tool.invoke({"content": "新格式记忆"})
    files = list(mem_root.glob("*.md"))
    assert len(files) == 1
    # 文件名格式：<timestamp>_<id>.md
    assert "_" in files[0].name
    # 不应写 MEMORY.md 索引（演示版简化，不动现有 MemoryStore 的 _refresh_index）
    assert not (mem_root / "MEMORY.md").exists()
