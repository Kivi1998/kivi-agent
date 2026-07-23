"""Mock Database Adapter（agent: package-db-real-v4）。

保留 query_database Tool 的 mock 语义：
- "users" / "orders" / "products" 三张内存表
- 简单解析 SELECT * FROM <table> [LIMIT n]
- 不抛错：未知表返回空列表；不可解析 SQL 返回空列表

设计取舍：演示版 SQL 模板（query_database._mock_step1_generate_sql）会生成
`SELECT * FROM products_<datasource_id>` 之类的语句；本 Adapter 按表名首段匹配
（即忽略 schema/ds 后缀，仅取 \\w+ 的第一个 token）。
"""

from __future__ import annotations

import re
from typing import Any

# Mock 数据（agent: package-db-real-v4）
MOCK_TABLES: dict[str, list[dict[str, Any]]] = {
    "users": [
        {"id": 1, "name": "Alice", "email": "alice@example.com", "created_at": "2026-01-15"},
        {"id": 2, "name": "Bob", "email": "bob@example.com", "created_at": "2026-02-20"},
        {"id": 3, "name": "Charlie", "email": "charlie@example.com", "created_at": "2026-03-10"},
    ],
    "orders": [
        {"id": 101, "user_id": 1, "product_id": 201, "amount": 99.5, "status": "paid"},
        {"id": 102, "user_id": 2, "product_id": 202, "amount": 150.0, "status": "pending"},
    ],
    "products": [
        {"id": 201, "name": "Widget", "price": 99.5, "category": "tools"},
        {"id": 202, "name": "Gadget", "price": 150.0, "category": "electronics"},
    ],
}


# 解析 SELECT * FROM <table> 形式；表名仅允许 \w+ 字符（防注入/防路径遍历）
_SELECT_RE = re.compile(r"select\s+\*\s+from\s+(\w+)", re.IGNORECASE)
_LIMIT_RE = re.compile(r"limit\s+(\d+)", re.IGNORECASE)


class MockAdapter:
    """Mock Adapter：内存表查询（agent: package-db-real-v4）。

    简单实现：解析 `SELECT * FROM <table> [LIMIT n]`，从 MOCK_TABLES 取数据。
    不支持的 SQL（无 SELECT * FROM）返回空列表，不抛错。
    """

    # 执行 SQL，返回行列表
    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        m = _SELECT_RE.search(sql)
        if not m:
            return []
        table = m.group(1)
        rows = list(MOCK_TABLES.get(table, []))
        m_limit = _LIMIT_RE.search(sql)
        if m_limit:
            rows = rows[: int(m_limit.group(1))]
        return rows

    # 健康检查：Mock 永远可用
    async def health_check(self) -> bool:
        return True

    # 关闭：Mock 无资源
    async def close(self) -> None:
        return None


# 对外暴露的符号（agent: package-db-real-v4）
__all__ = ["MockAdapter", "MOCK_TABLES"]
