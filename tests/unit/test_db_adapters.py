"""DatabaseAdapter 单元测试（agent: package-db-real-v4）。

覆盖 8 个测试：
- MockAdapter: 3（SELECT 解析 / LIMIT / 未知表 / 健康检查 / 关闭）
- SQLiteAdapter: 3（连接 / 真实 SQL / 健康检查）
- PostgresAdapter: 2（dict → positional 占位符 / 健康检查失败处理）

注：Postgres 真实连接不在本 WT 范围（E2E 才连），通过 fake pool 验证 execute 占位符展开逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kivi_agent.core.db.mock_adapter import MOCK_TABLES, MockAdapter
from kivi_agent.core.db.postgres_adapter import PostgresAdapter
from kivi_agent.core.db.sqlite_adapter import SQLiteAdapter

# --------------------------------------------------------------------------- #
# MockAdapter（3 个测试）
# --------------------------------------------------------------------------- #


# 功能：MockAdapter.execute 解析 SELECT * FROM users 并返回内存表数据
# 设计：直接命中 MOCK_TABLES["users"]；不依赖 LIMIT / WHERE 分支
async def test_mock_adapter_select_users() -> None:
    adapter = MockAdapter()
    rows = await adapter.execute("SELECT * FROM users")
    assert rows == MOCK_TABLES["users"]
    assert len(rows) == 3


# 功能：MockAdapter.execute 解析 LIMIT 子句并截断结果
# 设计：MockAdapter 应在 SQL 解析后对结果做 LIMIT 截断；这是 query_database 默认 mock 模式之外的协议级 mock
async def test_mock_adapter_limit_truncates() -> None:
    adapter = MockAdapter()
    rows = await adapter.execute("SELECT * FROM users LIMIT 2")
    assert len(rows) == 2
    # 大 LIMIT 也不应越界
    rows_all = await adapter.execute("SELECT * FROM users LIMIT 100")
    assert len(rows_all) == 3


# 功能：MockAdapter 对未知表 / 不可解析 SQL 返回空列表，不抛错
# 设计：健康检查在调用方需要宽松（fallback 时不应再被 mock 异常打断）；同时验证 health_check/close 幂等
async def test_mock_adapter_unknown_table_and_health() -> None:
    adapter = MockAdapter()
    unknown = await adapter.execute("SELECT * FROM no_such_table")
    assert unknown == []
    # 不可解析 SQL（无 FROM）也返回空
    garbage = await adapter.execute("garbage sql")
    assert garbage == []
    assert await adapter.health_check() is True
    # close 幂等
    await adapter.close()
    await adapter.close()


# --------------------------------------------------------------------------- #
# SQLiteAdapter（3 个测试）
# --------------------------------------------------------------------------- #


# 功能：SQLiteAdapter 接受 sqlite:/// DSN 与裸路径两种写法
# 设计：用 tmp_path 避免污染；分别验证 DSN 剥离与裸路径
async def test_sqlite_adapter_accepts_dsn_and_bare_path(tmp_path: Path) -> None:
    bare = tmp_path / "bare.db"
    dsn_path = tmp_path / "dsn.db"
    # 裸路径
    a1 = SQLiteAdapter(str(bare))
    assert a1._db_path == str(bare.resolve())
    await a1.close()
    # sqlite:/// DSN
    a2 = SQLiteAdapter(f"sqlite:///{dsn_path}")
    assert a2._db_path == str(dsn_path.resolve())
    await a2.close()


# 功能：SQLiteAdapter.execute 真跑 SQL：建表 → 插入 → 查询 → 拿回 rows
# 设计：用 tmp_path 隔离测试（每个测试一个独立 db 文件）；验证 SQL 真跑（行数 / 列名）
async def test_sqlite_adapter_execute_real_query(tmp_path: Path) -> None:
    db_file = tmp_path / "real.db"
    adapter = SQLiteAdapter(str(db_file))
    conn = await adapter._ensure_conn()
    await conn.execute("CREATE TABLE products_ds_1 (id INTEGER, name TEXT, price REAL)")
    await conn.execute("INSERT INTO products_ds_1 VALUES (1, 'Alpha', 99.5)")
    await conn.execute("INSERT INTO products_ds_1 VALUES (2, 'Beta', 50.0)")
    await conn.commit()
    rows = await adapter.execute("SELECT * FROM products_ds_1 ORDER BY id")
    assert len(rows) == 2
    assert rows[0]["name"] == "Alpha"
    assert rows[1]["price"] == 50.0
    await adapter.close()


# 功能：SQLiteAdapter 健康检查：可达 True；路径含 .. 抛 ValueError
# 设计：路径遍历保护是 Wave 4 硬约束；用合法 path 验证 True，用 ".." 触发 ValueError
async def test_sqlite_adapter_health_check_and_path_traversal(tmp_path: Path) -> None:
    # 合法路径 → 健康
    good = SQLiteAdapter(str(tmp_path / "ok.db"))
    assert await good.health_check() is True
    await good.close()
    # 路径遍历 → 抛 ValueError（不静默接受）
    with pytest.raises(ValueError, match="path traversal"):
        SQLiteAdapter(str(tmp_path / ".." / "evil.db"))


# --------------------------------------------------------------------------- #
# PostgresAdapter（2 个测试）
# --------------------------------------------------------------------------- #


class _FakePool:
    """模拟 asyncpg.Pool：记录 acquire 上下文与 fetch 调用参数。"""

    def __init__(self, fetch_rows: list[dict[str, Any]] | None = None) -> None:
        self._fetch_rows = fetch_rows or []
        self.acquired = 0
        self.last_sql: str | None = None
        self.last_args: tuple[Any, ...] = ()

    def acquire(self) -> _FakeAcquire:
        self.acquired += 1
        return _FakeAcquire(self)

    async def close(self) -> None:
        return None


class _FakeAcquire:
    def __init__(self, pool: _FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._pool)

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeConn:
    def __init__(self, pool: _FakePool) -> None:
        self._pool = pool

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self._pool.last_sql = sql
        self._pool.last_args = args
        return list(self._pool._fetch_rows)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return 1


class _BrokenPool:
    """健康检查失败：pool.acquire() 直接抛连接错误。"""

    def acquire(self) -> Any:
        raise ConnectionRefusedError("simulated postgres unreachable")

    async def close(self) -> None:
        return None


# 功能：PostgresAdapter.execute 把 dict params 展开为 positional args（$1/$2 替换）
# 设计：Postgres 用 $1/$2 而非 :name；adapter 接受 dict，展开顺序按 dict 插入序
async def test_postgres_adapter_dict_params_to_positional() -> None:
    adapter = PostgresAdapter("postgresql://user:pass@localhost:5432/db")
    pool = _FakePool(fetch_rows=[{"id": 1, "name": "x"}])
    # 注入 fake pool（绕过真实建连）
    adapter._pool = pool  # type: ignore[assignment]
    rows = await adapter.execute(
        "SELECT * FROM t WHERE id = $1 AND name = $2",
        {"id": 1, "name": "x"},
    )
    assert rows == [{"id": 1, "name": "x"}]
    assert pool.last_sql is not None
    assert pool.last_args == (1, "x")
    # 不传 params → 空 tuple（用新 pool 隔离上一次 fetch_rows，避免上次的 fetch_rows 干扰）
    pool2 = _FakePool(fetch_rows=[])
    adapter._pool = pool2  # type: ignore[assignment]
    await adapter.execute("SELECT 1")
    assert pool2.last_args == ()


# 功能：PostgresAdapter.health_check 在连接失败时返 False（不抛错）
# 设计：健康检查必须 catch 所有异常；用 broken pool 触发 ConnectionRefusedError 验证
async def test_postgres_adapter_health_check_returns_false_on_failure() -> None:
    adapter = PostgresAdapter("postgresql://user:pass@localhost:5432/db")
    adapter._pool = _BrokenPool()  # type: ignore[assignment]
    assert await adapter.health_check() is False
    # 关闭空 pool 也应幂等
    await adapter.close()
