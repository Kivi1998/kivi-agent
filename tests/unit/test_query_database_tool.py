"""query_database 业务 Tool 测试（agent: package-c-v1）。

覆盖：
- Tool 协议：name / category / input_schema 正确
- 返回结构：含 sql / rows / columns
- rows 至少 3 行
- 严格只读：sql 包含 SELECT 关键字
- 调用次数限制：超过 3 次返回 error
- 参数校验：缺 question 或 datasource_id 返回 schema_error
- 计数器 reset 方法
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from kivi_agent.core.business.query_database import (
    QueryDatabaseTool,
    _mock_step1_generate_sql,
    _mock_step2_execute,
)


@pytest.fixture(autouse=True)
def _reset_call_count() -> None:
    """每个测试前重置计数器，避免测试间相互影响。"""
    QueryDatabaseTool.reset_call_count()
    yield
    QueryDatabaseTool.reset_call_count()


# 功能：query_database Tool 协议字段正确
def test_query_database_tool_metadata() -> None:
    tool = QueryDatabaseTool()
    assert tool.name == "query_database"
    assert tool.category == "read"
    # question + datasource_id 都是必填
    assert set(tool.input_schema["required"]) == {"question", "datasource_id"}


# 功能：调用返回 sql / rows / columns
async def test_query_database_returns_expected_keys() -> None:
    tool = QueryDatabaseTool()
    result = await tool.invoke({"question": "上个月销售前 10", "datasource_id": "ds-sales-1"})
    assert not result.is_error
    data = json.loads(result.content)
    assert "sql" in data
    assert "rows" in data
    assert "columns" in data


# 功能：rows 至少 3 行
async def test_query_database_returns_at_least_three_rows() -> None:
    tool = QueryDatabaseTool()
    result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    data = json.loads(result.content)
    assert len(data["rows"]) >= 3


# 功能：columns 字段一致——columns 是 rows[0] 的键
async def test_query_database_columns_match_rows() -> None:
    tool = QueryDatabaseTool()
    result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    data = json.loads(result.content)
    assert set(data["columns"]) == set(data["rows"][0].keys())


# 功能：sql 是严格只读 SELECT（演示版约定）
async def test_query_database_sql_is_select_only() -> None:
    tool = QueryDatabaseTool()
    result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    data = json.loads(result.content)
    sql_upper = data["sql"].upper()
    assert "SELECT" in sql_upper
    # 禁止的写操作
    assert "INSERT" not in sql_upper
    assert "UPDATE" not in sql_upper
    assert "DELETE" not in sql_upper
    assert "DROP" not in sql_upper
    assert "TRUNCATE" not in sql_upper


# 功能：sql 包含用户 question 与 datasource_id（演示版注入）
async def test_query_database_sql_includes_question_and_ds() -> None:
    tool = QueryDatabaseTool()
    result = await tool.invoke({"question": "测试 Q", "datasource_id": "ds-X"})
    data = json.loads(result.content)
    assert "测试 Q" in data["sql"]
    assert "ds-X" in data["sql"]


# 功能：调用次数计数器——第一次返回正常，第二次 call_count=2
async def test_query_database_call_count_increments() -> None:
    tool = QueryDatabaseTool()
    r1 = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    d1 = json.loads(r1.content)
    assert d1["call_count"] == 1
    r2 = await tool.invoke({"question": "Y", "datasource_id": "ds-1"})
    d2 = json.loads(r2.content)
    assert d2["call_count"] == 2


# 功能：超过 3 次返回 error（C 报告 §3.10）
async def test_query_database_call_limit_3() -> None:
    tool = QueryDatabaseTool()
    # 前 3 次正常
    for i in range(3):
        r = await tool.invoke({"question": f"Q{i}", "datasource_id": "ds-1"})
        assert not r.is_error, f"第 {i+1} 次不应报错"
    # 第 4 次应被限制
    r4 = await tool.invoke({"question": "Q4", "datasource_id": "ds-1"})
    assert r4.is_error
    assert r4.error_type == "runtime_error"
    data = json.loads(r4.content)
    assert data["error"] == "call_limit_exceeded"
    assert data["limit"] == 3


# 功能：reset_call_count 后可重新调用
async def test_query_database_reset_clears_limit() -> None:
    tool = QueryDatabaseTool()
    for i in range(3):
        await tool.invoke({"question": f"Q{i}", "datasource_id": "ds-1"})
    # 第 4 次被限制
    r4 = await tool.invoke({"question": "Q4", "datasource_id": "ds-1"})
    assert r4.is_error
    # 重置后恢复
    QueryDatabaseTool.reset_call_count()
    r5 = await tool.invoke({"question": "Q5", "datasource_id": "ds-1"})
    assert not r5.is_error


# 功能：缺 question 返回 schema_error
async def test_query_database_missing_question() -> None:
    tool = QueryDatabaseTool()
    r = await tool.invoke({"datasource_id": "ds-1"})
    assert r.is_error
    assert r.error_type == "schema_error"


# 功能：缺 datasource_id 返回 schema_error
async def test_query_database_missing_datasource() -> None:
    tool = QueryDatabaseTool()
    r = await tool.invoke({"question": "X"})
    assert r.is_error
    assert r.error_type == "schema_error"


# 功能：question / datasource_id 类型错误返回 schema_error
async def test_query_database_invalid_types() -> None:
    tool = QueryDatabaseTool()
    r = await tool.invoke({"question": 123, "datasource_id": []})
    assert r.is_error
    assert r.error_type == "schema_error"


# 功能：_mock_step1_generate_sql 始终返回 SELECT
def test_mock_step1_sql_is_select() -> None:
    sql = _mock_step1_generate_sql("any", "ds-test")
    assert "SELECT" in sql.upper()


# 功能：_mock_step2_execute 返回 (rows, columns) 元组
def test_mock_step2_shape() -> None:
    rows, columns = _mock_step2_execute("SELECT 1", "ds-1")
    assert isinstance(rows, list)
    assert len(rows) >= 3
    assert isinstance(columns, list)
    assert columns == list(rows[0].keys())


# 功能：Pydantic 直接校验
def test_query_database_params_validation() -> None:
    from kivi_agent.core.business.query_database import QueryDatabaseParams

    p = QueryDatabaseParams.model_validate({"question": "X", "datasource_id": "ds-1"})
    assert p.question == "X"
    assert p.datasource_id == "ds-1"
    with pytest.raises(ValidationError):
        QueryDatabaseParams.model_validate({"question": "X"})
    with pytest.raises(ValidationError):
        QueryDatabaseParams.model_validate({"datasource_id": "ds-1"})
