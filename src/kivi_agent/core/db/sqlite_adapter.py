"""SQLite Adapter（agent: package-db-real-v4）。

用 aiosqlite 实现，支持 :param 占位符（防 SQL 注入）。
配置：DATABASE_URL=sqlite:///path/to/db.db 或裸路径。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)


class SQLiteAdapter:
    """SQLite Adapter：本地文件数据库（agent: package-db-real-v4）。

    支持 DSN：`sqlite:///path/to/db.db`（剥离前缀），也接受裸路径。
    使用 aiosqlite.Connection（单连接），通过 row_factory=Row 让 fetchall 返回可 dict 化的行。

    注意：
    - 演示版查询是只读 SELECT，无写操作；如未来允许写操作，需要在 execute() 入口做白名单校验。
    - in-memory DB（`:memory:`）的连接是独占的；测试场景下请复用同一 Adapter 实例。
    """

    def __init__(self, db_path: str) -> None:
        # 解析 DSN 前缀
        if db_path.startswith("sqlite:///"):
            path_str = db_path[len("sqlite:///") :]
        elif db_path.startswith("sqlite://"):
            # sqlite:// 形式（主机/内存）：保持原样，aiosqlite 也接受
            path_str = db_path
        else:
            path_str = db_path
        # 特殊值：内存数据库（":memory:"）保持原样不解析为文件路径（agent: package-db-real-v4）
        # 否则 Path(":memory:").expanduser().resolve() 会把 ":memory:" 当作文件名落盘
        if path_str == ":memory:":
            self._db_path: str = ":memory:"
            self._conn: aiosqlite.Connection | None = None
            return
        # 路径遍历保护：禁止出现 .. 路径段（agent: package-db-real-v4）
        # 业务上 db_path 来自配置，但做一次防御性校验避免误传
        if ".." in Path(path_str).parts:
            raise ValueError(
                f"Invalid SQLite database path (path traversal detected): {path_str!r}"
            )
        # 解析为绝对路径
        self._db_path = str(Path(path_str).expanduser().resolve())
        self._conn = None

    # 懒加载连接：首次访问时建连，单例复用
    async def _ensure_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            # 确保父目录存在
            parent = Path(self._db_path).parent
            if str(parent) and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    # 执行 SQL 并返回行列表（dict）
    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        conn = await self._ensure_conn()
        async with conn.execute(sql, params or {}) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    # 健康检查：执行 SELECT 1，能连返 True；不能连返 False（不抛错）
    async def health_check(self) -> bool:
        try:
            conn = await self._ensure_conn()
            async with conn.execute("SELECT 1") as cur:
                await cur.fetchone()
            return True
        except Exception as exc:  # noqa: BLE001 — 健康检查不抛错
            log.warning("SQLite health_check failed: %s", exc)
            return False

    # 关闭连接
    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


# 对外暴露的符号（agent: package-db-real-v4）
__all__ = ["SQLiteAdapter"]
