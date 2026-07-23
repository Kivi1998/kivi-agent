"""Memory Dashboard API 单元测试（WT-J3 / agent: package-dashboard-api-v61）。

测试目标：
1. 8 个端点的请求/响应 schema
2. MemoryItemStore Local/Vector 双路径（local always / vector optional）
3. 路径遍历保护（`..` in memory_id → 400）
4. vector 不可用时 fallback 到 local
5. _ensure_safe_memory_id / list / search / 各种 200 / 404 场景

设计要点：
- 用 `memory_dashboard.reset_memory_store_for_test()` 隔离单例
- tmp_path 注入 LocalMemoryBackend
- 不依赖 J1 (VectorMemoryBackend) / J2 (MemoryLifecycle/MemoryAuditLogger) 的实现
- 14+ 测试 = 8 端点 × 2 场景
"""

# tests/unit/test_memory_dashboard_api.py（agent: package-dashboard-api-v61）

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.local_backend import LocalMemoryBackend
from kivi_agent.core.memory.store import MemoryItemStore, reset_memory_store_for_test
from kivi_agent.gateway import memory_dashboard as memory_dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def mem_root(tmp_path: Path) -> Path:
    """临时 local backend 根目录（agent: package-dashboard-api-v61）。"""
    return tmp_path / "memory"


@pytest.fixture
def local_backend(mem_root: Path) -> LocalMemoryBackend:
    """构造 LocalMemoryBackend（agent: package-dashboard-api-v61）。"""
    return LocalMemoryBackend(root=mem_root)


@pytest.fixture
def store(local_backend: LocalMemoryBackend) -> MemoryItemStore:
    """构造 MemoryItemStore 并注入到 dashboard 单例（agent: package-dashboard-api-v61）。"""
    s = MemoryItemStore(local=local_backend)
    memory_dashboard_mod._memory_store = s
    yield s
    memory_dashboard_mod._memory_store = None
    reset_memory_store_for_test()


class _FakeRuntime:
    """FastAPI create_app 注入的 fake runtime。"""

    async def start_session(self, *args: Any, **kwargs: Any) -> Any:
        from kivi_agent.core.gateway.runtime import SessionInfo

        return SessionInfo(
            session_id="x",
            user_id="u",
            goal="g",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id=None,
        )

    async def cancel_session(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def list_sessions(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def get_session(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def send_command(self, *args: Any, **kwargs: Any) -> Any:
        return {}

    def subscribe_events(self, *args: Any, **kwargs: Any) -> Any:
        async def _gen() -> Any:
            if False:
                yield  # type: ignore[unreachable]

        return _gen()


@pytest.fixture
def client(store: MemoryItemStore) -> TestClient:
    """FastAPI TestClient + memory store 注入（agent: package-dashboard-api-v61）。"""
    app = create_app(runtime=_FakeRuntime())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


# ---- 工具函数 --------------------------------------------------------------


def _make_item(**kwargs: Any) -> MemoryItem:
    """构造 MemoryItem（agent: package-dashboard-api-v61）。"""
    defaults: dict[str, Any] = {
        "id": "m-1",
        "content": "hello world",
        "memory_type": "user",
        "importance": 0.5,
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": None,
    }
    defaults.update(kwargs)
    return MemoryItem(**defaults)


# ---- /items 端点测试 -------------------------------------------------------


# 功能：items 端点空 store 时返回 total=0 + items=[]
# 设计：fresh store → 0 条记忆，断言 total=0 / items=[] / backend=local
def test_list_items_empty(client: TestClient) -> None:
    resp = client.get("/api/memory/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["backend"] == "local"


# 功能：items 端点按 status / memory_type 过滤
# 设计：写 3 条（active×2 + archived×1）→ status=active 返回 2 条；
#      memory_type=feedback 返回 0 条
def test_list_items_with_filters(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(
            _make_item(id="m-1", status="active", memory_type="user")
        )
        await store.write(
            _make_item(id="m-2", status="active", memory_type="feedback")
        )
        await store.write(
            _make_item(id="m-3", status="archived", memory_type="user")
        )

    asyncio.run(_seed())

    r1 = client.get("/api/memory/items?status=active")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["total"] == 2
    assert {i["id"] for i in body1["items"]} == {"m-1", "m-2"}

    r2 = client.get("/api/memory/items?memory_type=feedback")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["total"] == 1
    assert body2["items"][0]["id"] == "m-2"


# ---- /items/{id} 端点测试 --------------------------------------------------


# 功能：items/{id} 不存在时返回 404
# 设计：空 store + 随机 id → 404 + detail 含 id
def test_get_item_not_found(client: TestClient) -> None:
    resp = client.get("/api/memory/items/missing-id")
    assert resp.status_code == 404
    assert "missing-id" in resp.json()["detail"]


# 功能：items/{id} 存在时返回完整字段
# 设计：写 1 条 → 读出 → 断言 7 字段全等
def test_get_item_detail(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(
            _make_item(
                id="m-detail",
                content="detailed",
                memory_type="feedback",
                importance=0.8,
                status="active",
                expires_at="2027-01-01T00:00:00Z",
            )
        )

    asyncio.run(_seed())

    resp = client.get("/api/memory/items/m-detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "m-detail"
    assert body["content"] == "detailed"
    assert body["memory_type"] == "feedback"
    assert body["importance"] == 0.8
    assert body["status"] == "active"
    assert body["expires_at"] == "2027-01-01T00:00:00Z"


# ---- /items POST 端点测试 --------------------------------------------------


# 功能：POST /items 必填字段校验：缺 content → 400
# 设计：空 body → 422（FastAPI 自动）/ 空 content → 400
def test_create_item_missing_content(client: TestClient) -> None:
    resp = client.post("/api/memory/items", json={"memory_type": "user"})
    assert resp.status_code == 400
    assert "content" in resp.json()["detail"]


# 功能：POST /items 必填字段校验：缺 memory_type → 400
# 设计：仅传 content → 400
def test_create_item_missing_memory_type(client: TestClient) -> None:
    resp = client.post("/api/memory/items", json={"content": "x"})
    assert resp.status_code == 400
    assert "memory_type" in resp.json()["detail"]


# 功能：POST /items 正常创建（自动生成 id + 写盘）
# 设计：传 content + memory_type → 201，断言响应有 id / content / status=active；
#      同时通过 store.read 验证已落盘
def test_create_item_success(
    client: TestClient, store: MemoryItemStore
) -> None:
    resp = client.post(
        "/api/memory/items",
        json={
            "content": "I prefer dark mode",
            "memory_type": "user",
            "importance": 0.7,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "I prefer dark mode"
    assert body["memory_type"] == "user"
    assert body["importance"] == 0.7
    assert body["status"] == "active"
    assert body["id"].startswith("m-")
    # 落盘验证
    import asyncio

    got = asyncio.run(store.read(body["id"]))
    assert got is not None
    assert got.content == "I prefer dark mode"


# 功能：POST /items importance 超出 [0,1] → 400
# 设计：importance=1.5 → 400
def test_create_item_importance_out_of_range(client: TestClient) -> None:
    resp = client.post(
        "/api/memory/items",
        json={"content": "x", "memory_type": "user", "importance": 1.5},
    )
    assert resp.status_code == 400
    assert "importance" in resp.json()["detail"]


# ---- /items/{id} PATCH 端点测试 --------------------------------------------


# 功能：PATCH /items/{id} 不存在 → 404
# 设计：空 store → PATCH → 404
def test_update_item_not_found(client: TestClient) -> None:
    resp = client.patch(
        "/api/memory/items/missing", json={"content": "new"}
    )
    assert resp.status_code == 404


# 功能：PATCH /items/{id} 部分更新：只改 content，其他字段保留
# 设计：write 一条 → PATCH content → read 验证 content 变了 / 其他不变
def test_update_item_partial(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(
            _make_item(
                id="m-up",
                content="old",
                memory_type="user",
                importance=0.5,
            )
        )

    asyncio.run(_seed())

    resp = client.patch(
        "/api/memory/items/m-up", json={"content": "new content"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "new content"
    # 其他字段保留
    assert body["memory_type"] == "user"
    assert body["importance"] == 0.5
    assert body["id"] == "m-up"

    # 落盘验证
    got = asyncio.run(store.read("m-up"))
    assert got is not None
    assert got.content == "new content"


# ---- /items/{id} DELETE 端点测试 -------------------------------------------


# 功能：DELETE /items/{id} 不存在 → 404
# 设计：空 store → DELETE → 404
def test_delete_item_not_found(client: TestClient) -> None:
    resp = client.delete("/api/memory/items/missing")
    assert resp.status_code == 404


# 功能：DELETE /items/{id} 成功删除 + 写审计
# 设计：write 一条 → DELETE → 200 {deleted: true}；
#      read 验证返回 None；audit.log 含 delete 事件
def test_delete_item_success(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-del"))

    asyncio.run(_seed())

    resp = client.delete("/api/memory/items/m-del")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["memory_id"] == "m-del"

    # 落盘验证：read 返回 None
    got = asyncio.run(store.read("m-del"))
    assert got is None

    # 审计验证
    log_path = store.get_local().root / "audit.log"
    assert log_path.exists()
    text = log_path.read_text(encoding="utf-8")
    assert "m-del" in text
    assert "delete" in text


# ---- /items/{id}/archive 端点测试 ------------------------------------------


# 功能：archive 端点把 status 改为 archived
# 设计：write 一条 active → POST archive → 200 + status=archived
def test_archive_item_success(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-arc", status="active"))

    asyncio.run(_seed())

    resp = client.post("/api/memory/items/m-arc/archive")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "m-arc"
    assert body["status"] == "archived"

    # 落盘验证
    got = asyncio.run(store.read("m-arc"))
    assert got is not None
    assert got.status == "archived"


# 功能：archive 端点 memory 不存在 → 404
# 设计：空 store → POST archive → 404
def test_archive_item_not_found(client: TestClient) -> None:
    resp = client.post("/api/memory/items/missing/archive")
    assert resp.status_code == 404


# ---- /search 端点测试 ------------------------------------------------------


# 功能：search 无 vector backend 时走 local substring 检索
# 设计：写 3 条（1 含 "alpha"，1 含 "alpha+beta"，1 不含）→ search "alpha"
#      → 返回 2 条，backend=local
def test_search_local_fallback(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-1", content="alpha content"))
        await store.write(
            _make_item(id="m-2", content="beta and alpha together")
        )
        await store.write(_make_item(id="m-3", content="pure beta"))

    asyncio.run(_seed())

    resp = client.get("/api/memory/search?q=alpha&top_k=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "local"
    assert body["query"] == "alpha"
    assert body["top_k"] == 5
    assert body["count"] == 2
    ids = {r["id"] for r in body["results"]}
    assert ids == {"m-1", "m-2"}


# 功能：search vector backend 可用时优先走 vector
# 设计：mock vector backend，验证 search 走 vector，assert backend=vector
def test_search_uses_vector_when_available(
    client: TestClient, store: MemoryItemStore
) -> None:
    # 注入 mock vector backend
    class _MockVector:
        def __init__(self) -> None:
            self.search_called = False

        async def search(
            self, query: str, top_k: int = 5
        ) -> list[MemoryItem]:
            self.search_called = True
            return [
                _make_item(id="v-1", content=f"vector hit for {query}"),
            ]

    mock_vec = _MockVector()
    store.set_vector(mock_vec)  # type: ignore[arg-defined]

    resp = client.get("/api/memory/search?q=anything&top_k=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "vector"
    assert body["count"] == 1
    assert body["results"][0]["id"] == "v-1"
    assert mock_vec.search_called is True


# 功能：search vector 抛异常时 fallback 到 local
# 设计：mock vector 抛 RuntimeError，验证走 local substring
def test_search_falls_back_to_local_on_vector_error(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-1", content="alpha bravo"))

    asyncio.run(_seed())

    class _BrokenVector:
        async def search(
            self, query: str, top_k: int = 5
        ) -> list[MemoryItem]:
            raise RuntimeError("ES down")

    store.set_vector(_BrokenVector())  # type: ignore[arg-defined]

    resp = client.get("/api/memory/search?q=alpha")
    assert resp.status_code == 200
    body = resp.json()
    # vector 抛异常 → fallback local
    assert body["backend"] == "local"
    assert body["count"] == 1


# ---- /audit 端点测试 -------------------------------------------------------


# 功能：audit 端点返回某 memory_id 的全部审计事件
# 设计：write + delete + 写 audit → audit 端点返回 2 事件
def test_audit_list_events(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-aud"))
        await store.audit(
            MemoryAuditEvent(
                memory_id="m-aud",
                event_type="create",
                ts="2026-01-01T00:00:00Z",
                actor="admin:dashboard",
            )
        )
        await store.audit(
            MemoryAuditEvent(
                memory_id="m-aud",
                event_type="update",
                ts="2026-01-01T00:00:05Z",
                actor="admin:dashboard",
            )
        )

    asyncio.run(_seed())

    resp = client.get("/api/memory/audit?memory_id=m-aud")
    assert resp.status_code == 200
    body = resp.json()
    assert body["memory_id"] == "m-aud"
    assert body["total"] == 2
    event_types = {e["event_type"] for e in body["events"]}
    assert {"create", "update"}.issubset(event_types)


# 功能：audit 端点对无审计的 memory 返回 total=0
# 设计：只 write 不 audit → total=0
def test_audit_empty(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.write(_make_item(id="m-empty"))

    asyncio.run(_seed())

    resp = client.get("/api/memory/audit?memory_id=m-empty")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["events"] == []


# ---- 路径遍历保护测试 -----------------------------------------------------


# 功能：memory_id 含 `..` 时返回 400（路径遍历保护）
# 设计：覆盖 6 个动态路由（list 已分页无 id，items/{id} 4 个 + audit 1 个）
def test_path_traversal_memory_id(client: TestClient) -> None:
    r1 = client.get("/api/memory/items/..bad..")
    assert r1.status_code == 400
    r2 = client.patch("/api/memory/items/..bad..", json={"content": "x"})
    assert r2.status_code == 400
    r3 = client.delete("/api/memory/items/..bad..")
    assert r3.status_code == 400
    r4 = client.post("/api/memory/items/..bad../archive")
    assert r4.status_code == 400
    r5 = client.get("/api/memory/audit?memory_id=..bad..")
    assert r5.status_code == 400
    assert "invalid memory_id" in r1.json()["detail"]


# ---- 单例管理测试 ---------------------------------------------------------


# 功能：reset_memory_store_for_test 后再 get_memory_store 会重建单例
# 设计：set → reset → 重新 get 返回新实例
def test_reset_memory_store_for_test() -> None:
    from pathlib import Path as P

    fake_local = LocalMemoryBackend(root=P("/tmp/test_reset_memory"))
    custom = MemoryItemStore(local=fake_local)
    memory_dashboard_mod._memory_store = custom
    assert memory_dashboard_mod.get_memory_store() is custom
    memory_dashboard_mod.reset_memory_store_for_test()
    default = memory_dashboard_mod.get_memory_store()
    assert default is not custom
    memory_dashboard_mod.reset_memory_store_for_test()


# ---- J2 import 探测路径测试（不强制 J2 存在） -----------------------------


# 功能：audit 端点在 J2 模块未配置时仍能正常返回（fallback local）
# 设计：J2 未合并时 audit 走 local audit.log，验证 backend=local
def test_audit_falls_back_to_local_when_j2_missing(
    client: TestClient, store: MemoryItemStore
) -> None:
    import asyncio

    async def _seed() -> None:
        await store.audit(
            MemoryAuditEvent(
                memory_id="m-fallback",
                event_type="create",
                ts="2026-01-01T00:00:00Z",
                actor="system",
            )
        )

    asyncio.run(_seed())

    # 确保 J2 模块不在 sys.modules（默认就不在）
    sys.modules.pop("kivi_agent.core.memory.audit", None)

    resp = client.get("/api/memory/audit?memory_id=m-fallback")
    assert resp.status_code == 200
    body = resp.json()
    # J2 不存在时 backend=local
    assert body["backend"] == "local"
    assert body["total"] == 1


# 功能：audit 端点在 J2 模块（mock）存在时 backend 标识为 audit_logger
# 设计：构造一个 fake kivi_agent.core.memory.audit 模块让 find_spec 命中
def test_audit_backend_hint_when_j2_present(
    client: TestClient, store: MemoryItemStore
) -> None:
    # 注入一个 fake audit 模块让 find_spec 命中
    fake_audit = types.ModuleType("kivi_agent.core.memory.audit")
    sys.modules["kivi_agent.core.memory.audit"] = fake_audit
    try:
        resp = client.get("/api/memory/audit?memory_id=anything")
        assert resp.status_code == 200
        body = resp.json()
        assert body["backend"] == "audit_logger"
    finally:
        sys.modules.pop("kivi_agent.core.memory.audit", None)
