# kivi-agent Wave 4 E2E（agent: package-e2e-real-v4）

真实接入路径 E2E：本地 rag-kb mock + SQLite/Postgres + 健康检查降级。

> **目标**：验证 Wave 4 的 **Adapter / Mock / 配置 / 切换 / 降级** 五件套在真实
> HTTP / SQL 调用下行为正确，**不依赖** 生产 rag-kb 或生产 DB。
> 范围与任务参见 `docs/superpowers/plans/2026-07-23-aigroup-wave4-real-rag-db.md` §三 WT-F4。

## 文件清单

| 路径 | 作用 |
|---|---|
| `tests/fixtures/rag_kb_mock_server.py` | FastAPI in-process rag-kb mock（含 `InProcessRagKbServer`） |
| `docker-compose.test.yml` | Postgres 16-alpine 测试 DB（端口 5432，凭据 kivi_test） |
| `tests/sql/init.sql` | 通用 SQL 种子（users × 3 + orders × 3，SQLite/Postgres 通用） |
| `tests/e2e_real/conftest.py` | NO_PROXY 旁路 + `rag_server` / `postgres_dsn` fixtures |
| `tests/e2e_real/test_rag_real.py` | 4 个 rag-kb 真实模式场景 |
| `tests/e2e_real/test_db_real.py` | 4 个 DB Adapter 真实模式场景 |
| `tests/e2e_real/test_fallback.py` | 3 个健康检查 + 降级机制场景 |

## 复现步骤

### 1. 仅 SQLite + mock rag-kb（无需 Docker）

```bash
cd /Users/kivi/Documents/agent系统/Kama/kivi-agent-wt-wave4-e2e
uv run pytest tests/e2e_real -v
```

**期望输出**：`11 passed in ~3s`（4 RAG + 4 DB + 3 fallback）

### 2. 跑单个文件

```bash
uv run pytest tests/e2e_real/test_rag_real.py -v
uv run pytest tests/e2e_real/test_db_real.py -v
uv run pytest tests/e2e_real/test_fallback.py -v
```

### 3. Postgres 真实接入（需要 Docker）

```bash
# 启动 Postgres
docker-compose -f docker-compose.test.yml up -d

# 等 5-10s 让 init.sql 跑完
sleep 8

# 验证容器就绪
docker-compose -f docker-compose.test.yml ps
# 应显示 kivi-agent-pg-test 状态为 "Up (healthy)"

# （可选）手动连一下确认种子数据落地
docker exec -it kivi-agent-pg-test psql -U kivi_test -d kivi_test -c "SELECT * FROM users;"
# 期望：3 行（Alice / Bob / Charlie）

# 跑 Postgres 真实接入（需先有 asyncpg；当前 pyproject 未声明，跳过）
# DATABASE_URL=postgresql://kivi_test:kivi_test@127.0.0.1:5432/kivi_test \
#   uv run pytest tests/e2e_real/test_db_real.py -v

# 关闭
docker-compose -f docker-compose.test.yml down
```

> **注意**：Postgres E2E 场景需要 `asyncpg` 包，当前 `pyproject.toml` 未声明。
> WT-F2 合并后会补 `aiosqlite` + `asyncpg` 依赖，届时本 README 的 Postgres
> 段落会自动启用。F4 仅做 SQL 种子可复现性验证（用 sqlite3 直跑 init.sql）。

## 设计要点

### 1. mock rag-kb in-process 启动

`InProcessRagKbServer` 用 `uvicorn.Server` + 后台线程在 pytest 进程内起
FastAPI，监听随机端口（`port=0`）。`start()` 返回 `http://127.0.0.1:<port>`
供测试用 httpx 直连。`stop()` 触发 `should_exit` + 线程 join。

| 端点 | 行为 |
|---|---|
| `GET /health` | `{"status": "ok", "kb_id": "<id>"}` |
| `POST /api/v1/search` | `{"answer": ..., "rewritten_query": ..., "sources": [...]}` |

### 2. 本地代理旁路

开发机常设 `http_proxy=...:7897`（Clash / SSR），会拦截 `127.0.0.1` 返回 502。
`tests/e2e_real/conftest.py` 在 import 时立即把 `127.0.0.1` / `localhost` / `::1`
加入 `NO_PROXY`，确保 mock server 与 httpx 客户端直连。

### 3. 通用 SQL 种子

`tests/sql/init.sql` 用 SQLite / Postgres 通用子集：
- `INTEGER PRIMARY KEY`（不用 `SERIAL` / `AUTOINCREMENT`）
- `TEXT`（不用 `VARCHAR`）
- `NUMERIC(10, 2)`（不用 `DECIMAL`）
- `TEXT DEFAULT CURRENT_TIMESTAMP`（不用 `TIMESTAMP DEFAULT NOW()`）

种子 3 user + 3 order，覆盖 paid/pending 状态组合，便于 JOIN 聚合断言。

### 4. 降级契约对齐 F3

`test_fallback.py` 用本地最小 `_build_minimal_health_router` 复现 F3
`/health/detailed` 的契约（200 全健康 / 207 部分降级）。F3 合并后，本测试可
改为 `from kivi_agent.gateway.health import build_health_router` 并直接用真实
router；测试断言逻辑保持不变。

## 故障排查

| 现象 | 原因 | 修复 |
|---|---|---|
| `httpx.ConnectError` on 127.0.0.1 | 本地代理拦截 | 检查 `NO_PROXY` 是否含 127.0.0.1；conftest 已自动设置 |
| `502 Bad Gateway` from proxy | 同上 | 同上；或临时 `unset http_proxy` 再跑 |
| `sqlite3.OperationalError: near "("` | SQL 用了 Postgres 专属类型 | 用通用子集；见 `tests/sql/init.sql` |
| `docker-compose up` 后健康检查一直不绿 | 5432 被本机 Postgres 占用 | 停本机 Postgres 或改 `ports` 映射 |
| `test_rag_real_fallback_when_server_stopped` 偶发失败 | 端口释放需要时间 | fixture 内已 sleep 0.3s，可调到 0.5s |
| `ModuleNotFoundError: kivi_agent.core.rag` | F1 未合并 | F4 测试不直接依赖 F1；F1 合并后跑 rag 真实路径 E2E |

## 与 Wave 4 其它 WT 的边界

- **WT-F1（RAG HTTP 客户端）**：F1 合并后，`RagKbClient` 应能直接连本 mock server；
  本 E2E 已提供完整 REST 契约供其参考。
- **WT-F2（DB Adapter）**：F2 合并后，`SQLiteAdapter` / `PostgresAdapter` 应能
  读 `tests/sql/init.sql`；本 E2E 已用 sqlite3 验证种子的可复现性。
- **WT-F3（配置 + 健康检查）**：F3 合并后，`build_health_router` 可直接接本
  E2E 的 mock rag-kb；`/health/detailed` 的 200/207 契约已在本测试中锁定。

> F1 / F2 / F3 合并到 `integration/aigroup-wave4-e2e` 后，本 README 顶部的
> "期望输出 11 passed" 应升级为 11 + (F1 F2 F3 新增 E2E) passed。
