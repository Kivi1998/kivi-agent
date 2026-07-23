"""数据库 Adapter 真实模式 E2E（agent: package-e2e-real-v4）。

WT-F4 E2E 场景：用 ``tests/sql/init.sql`` 的种子数据 + ``sqlite3`` 内置驱动
验证 Database Adapter 真实模式下的 SQL 执行路径（不依赖 asyncpg，避免装包）。

4 个场景：
1. ``test_sqlite_real_loads_seed_schema`` — init.sql 能建出 users + orders 表
2. ``test_sqlite_real_queries_seeded_data`` — 种子数据可查（3 user / 3 order）
3. ``test_sqlite_real_join_users_orders`` — JOIN 跨表查询
4. ``test_db_real_invalid_path_raises_error`` — 无效路径显式失败（fallback 触发条件）

依赖：仅 ``sqlite3``（Python 内置）+ ``asyncio.to_thread``。
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import cast

import pytest

# 种子 SQL 路径（agent: package-e2e-real-v4）
SEED_SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "init.sql"


# 在线程池里跑同步 sqlite3 调用（agent: package-e2e-real-v4）
async def _sqlite_exec(
    db_path: str, sql: str, params: tuple[object, ...] = ()
) -> list[dict[str, object]]:
    """在 default executor 跑 sqlite3，IO 阻塞不卡 event loop。

    单 SELECT / INSERT 用 ``execute``；多语句脚本（init.sql）自动改用
    ``executescript``，调用方无需区分。
    """
    def _run() -> list[dict[str, object]]:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            # 简单启发：含 ;\n 的脚本走 executescript（CREATE/INSERT 混合）
            if ";\n" in sql or sql.count(";") > 1:
                conn.executescript(sql)
                conn.commit()
                return []
            cur = conn.execute(sql, params)
            try:
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                # 非 SELECT（CREATE / INSERT）时 fetchall 报 "no results"
                conn.commit()
                return []
            return [dict(r) for r in rows]

    return await asyncio.to_thread(_run)


# 功能：tests/sql/init.sql 能在临时 SQLite 上成功建表 + 插入种子数据
# 设计：用 tempfile 创建临时 DB → 在线程池里 exec init.sql → 查 sqlite_master
#      确认 users / orders 两张表都已建出；这是 E2E 验证 SQL 种子可复现的核心场景
async def test_sqlite_real_loads_seed_schema() -> None:
    assert SEED_SQL_PATH.exists(), f"seed SQL not found: {SEED_SQL_PATH}"
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        await _sqlite_exec(db_path, sql)
        # 查 sqlite_master 确认两表都建出
        tables = await _sqlite_exec(
            db_path,
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'orders') ORDER BY name",  # noqa: E501
        )
        names = [t["name"] for t in tables]
        assert "users" in names
        assert "orders" in names
    finally:
        os.unlink(db_path)


# 功能：种子数据可查——users 表 3 条（Alice/Bob/Charlie），orders 表 3 条
# 设计：init.sql 是固定种子，断言精确行数与已知 ID/name 列表；这是 Wave 4
#      数据库 Adapter 真实模式"读到的是 docker 里的真数据"的最小可验证
async def test_sqlite_real_queries_seeded_data() -> None:
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        await _sqlite_exec(db_path, sql)
        # users 3 条
        users = await _sqlite_exec(db_path, "SELECT id, name FROM users ORDER BY id")
        assert len(users) == 3
        assert [u["name"] for u in users] == ["Alice", "Bob", "Charlie"]
        # orders 3 条
        orders = await _sqlite_exec(
            db_path, "SELECT user_id, amount, status FROM orders ORDER BY id"
        )
        assert len(orders) == 3
        assert orders[0]["status"] == "paid"
        assert orders[1]["status"] == "pending"
    finally:
        os.unlink(db_path)


# 功能：users + orders 跨表 JOIN 验证外键与查询路径真实可用
# 设计：JOIN 是数据库 Adapter 的核心场景（query_database Tool 经常用）；
#      用 SUM(amount) 聚合每个用户的订单总额，验证 SQLite 真执行了聚合而非 mock
async def test_sqlite_real_join_users_orders() -> None:
    sql = SEED_SQL_PATH.read_text(encoding="utf-8")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        await _sqlite_exec(db_path, sql)
        joined = await _sqlite_exec(
            db_path,
            """
            SELECT u.name, COALESCE(SUM(o.amount), 0) AS total
            FROM users u LEFT JOIN orders o ON u.id = o.user_id
            GROUP BY u.id, u.name
            ORDER BY u.id
            """,
        )
        assert len(joined) == 3
        # Alice: 1 个 paid 订单 99.50；Bob: 1 个 pending 150；Charlie: 1 个 paid 250
        # total 字段 SQLite 读出来是 float（NUMERIC → REAL）；cast 一下避开 object 报错
        assert joined[0]["name"] == "Alice"
        assert abs(cast(float, joined[0]["total"]) - 99.50) < 0.01
        assert joined[1]["name"] == "Bob"
        assert abs(cast(float, joined[1]["total"]) - 150.00) < 0.01
        assert joined[2]["name"] == "Charlie"
        assert abs(cast(float, joined[2]["total"]) - 250.00) < 0.01
    finally:
        os.unlink(db_path)


# 功能：DB 路径无效时，SQLite 显式抛错（Database Adapter 据此触发降级到 Mock）
# 设计：用一个不存在的目录路径调 sqlite3.connect，期望 sqlite3.OperationalError
#      抛出；这是 Wave 4 切换机制的核心信号——"真实 DB 不可用"必须能被检测到
async def test_db_real_invalid_path_raises_error() -> None:
    invalid_path = "/nonexistent_dir_for_db_e2e_test/db.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        # 故意同步调，捕获 sqlite3 自身抛的错误类型
        with sqlite3.connect(invalid_path) as conn:
            conn.execute("SELECT 1")
