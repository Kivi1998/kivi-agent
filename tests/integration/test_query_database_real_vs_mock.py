"""query_database Tool 真实模式 vs Mock 模式集成测试（agent: package-db-real-v4）。

3 场景：
1. test_mock_mode_default：无 adapter → 默认 mock 模式（保留 14 个原始行为）
2. test_real_mode_uses_adapter：传 SQLite adapter → 走真实 SQL，response 包含 DB 数据
3. test_fallback_on_adapter_error：adapter 抛错 → 降级到 mock 模式 + 记 warn 日志
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kivi_agent.core.business.query_database import QueryDatabaseTool
from kivi_agent.core.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture(autouse=True)
def _reset_call_count() -> None:
    """每个测试前重置计数器，避免测试间相互影响。"""
    QueryDatabaseTool.reset_call_count()
    yield
    QueryDatabaseTool.reset_call_count()


# 功能：QueryDatabaseTool 无 adapter 时走默认 mock 模式，返回固定 3 行 + sql/rows/columns
# 设计：默认构造器是 backward-compat 路径（无 Wave 4 之前的测试依赖），必须保持 3 行 + SELECT 模板
async def test_mock_mode_default() -> None:
    tool = QueryDatabaseTool()  # 无 adapter
    result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    assert not result.is_error
    data = json.loads(result.content)
    assert data["mode"] == "mock"
    assert len(data["rows"]) >= 3
    assert "SELECT" in data["sql"].upper()
    assert set(data["columns"]) == set(data["rows"][0].keys())


# 功能：QueryDatabaseTool 传 SQLite adapter 时走真实 SQL，response rows 来自 DB
# 设计：演示版默认模板生成 `SELECT * FROM products_ds_1 LIMIT 10`；用 tmp_path SQLite 真建表
async def test_real_mode_uses_adapter(tmp_path: Path) -> None:
    db_file = tmp_path / "real.db"
    adapter = SQLiteAdapter(str(db_file))
    # 预建表 products_ds_1（与默认 SQL 模板的表名匹配）
    conn = await adapter._ensure_conn()
    await conn.execute("CREATE TABLE products_ds_1 (id INTEGER, name TEXT, price REAL)")
    await conn.execute("INSERT INTO products_ds_1 VALUES (1, 'Alpha', 99.5)")
    await conn.execute("INSERT INTO products_ds_1 VALUES (2, 'Beta', 50.0)")
    await conn.commit()
    tool = QueryDatabaseTool(adapter=adapter)
    try:
        result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
        assert not result.is_error
        data = json.loads(result.content)
        assert data["mode"] == "real"
        # 真实 DB 返回的 rows 是预插入的 2 行
        assert len(data["rows"]) == 2
        names = {r["name"] for r in data["rows"]}
        assert names == {"Alpha", "Beta"}
    finally:
        await adapter.close()


# 功能：adapter 抛错时 QueryDatabaseTool 降级到 mock 模式（real_fallback）并记 warn 日志
# 设计：继承 SQLiteAdapter 让 isinstance 判定通过；覆写 execute 让它抛错；验证 mode=real_fallback
class _BrokenSQLiteAdapter(SQLiteAdapter):
    """继承 SQLiteAdapter 让 isinstance 判定通过（agent: package-db-real-v4）。

    覆写 execute 让它抛 RuntimeError，模拟真实 DB 不可用。
    """

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raise RuntimeError("simulated DB outage")


async def test_fallback_on_adapter_error(caplog: pytest.LogCaptureFixture) -> None:
    tool = QueryDatabaseTool(adapter=_BrokenSQLiteAdapter(":memory:"))
    with caplog.at_level("WARNING"):
        result = await tool.invoke({"question": "X", "datasource_id": "ds-1"})
    assert not result.is_error
    data = json.loads(result.content)
    # 降级到 mock 模式：rows 来自默认 mock step2（>= 3 行）
    assert data["mode"] == "real_fallback"
    assert len(data["rows"]) >= 3
    # 验证有 warn 日志
    assert any("falling back to mock" in rec.message for rec in caplog.records)
