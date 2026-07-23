"""Postgres Adapter（agent: package-db-real-v4）。

用 asyncpg 实现，**仅在 E2E / testcontainers 场景使用**。
生产数据库不在 Wave 4 范围（用户决定）。

占位符说明：本 Adapter 接受 dict[str, Any] 形式的 params；执行前将 dict
按 key 顺序展开为 positional args（asyncpg 用 $1 / $2 占位符）。
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

log = logging.getLogger(__name__)


class PostgresAdapter:
    """Postgres Adapter（agent: package-db-real-v4）。

    配置：DATABASE_URL=postgresql://user:pass@host:port/db
    使用 asyncpg 连接池（min_size=1, max_size=5）。
    """

    def __init__(self, dsn: str) -> None:
        # DSN 仅来自配置或测试夹具；不做路径遍历校验（DSN 是 URL 不是文件路径）
        self._dsn: str = dsn
        self._pool: asyncpg.Pool | None = None

    # 懒加载连接池
    async def _ensure_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        return self._pool

    # 执行 SQL，将 dict params 展开为 positional args
    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        pool = await self._ensure_pool()
        positional: tuple[Any, ...] = tuple(params.values()) if params else ()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *positional)
        return [dict(row) for row in rows]

    # 健康检查：能连返 True；不能连返 False（不抛错）
    async def health_check(self) -> bool:
        try:
            pool = await self._ensure_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as exc:  # noqa: BLE001 — 健康检查不抛错
            log.warning("Postgres health_check failed: %s", exc)
            return False

    # 关闭连接池
    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


# 对外暴露的符号（agent: package-db-real-v4）
__all__ = ["PostgresAdapter"]
