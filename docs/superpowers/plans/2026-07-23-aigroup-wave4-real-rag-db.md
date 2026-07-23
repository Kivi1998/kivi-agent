# aigroup Wave 4：真实 rag-kb API 接入 + 数据库 Adapter 架构

> **基线**：`main @ 3549a80`（aigroup Wave 3 Web Chat 收官）
> **日期**：2026-07-23
> **承接关系**：用户 2026-07-23 选定 "选 B 真实 RAG/DB 接入" + "选 A 本地 Docker 替代" + "多 worktree 并行"
> **不做**：接生产数据库 / 接云端 Key / 迁移或重写 rag-kb / Vector Memory 真实实现（留 Wave 5）/ Eval Dashboard（留 Wave 6）

---

## 一、目标

把 Wave 1 C 包 `rag_query` / `query_database` / `LocalMemoryBackend` 三个 Mock 升级为**可配置 Adapter + 真实服务调用**架构：

- **rag_query**：HTTP 客户端调用本地 rag-kb API（`http://localhost:8001`）
- **query_database**：Database Adapter 协议 + Postgres / SQLite Adapter 实现
- **所有 Adapter**：可降级到 Mock；启动时探测健康；不健康自动回退
- **配置系统**：环境变量 + TOML 配置文件
- **健康检查**：启动时 + 定期 + 暴露端点

**关键边界**（用户 2026-07-23 决定）：
- kivi-agent 通过 HTTP API 调用 rag-kb，**不迁移 / 不重写 rag-kb**
- 数据库：可配置 Adapter + Mock 保底，**不接生产数据库**
- 不用真实云服务 / Key
- rag-kb 本地起不来 → 保留 Mock + 完成 Adapter / 配置 / 健康检查 / 切换机制

---

## 二、范围

### 2.1 必做（Wave 4 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| F1 | RAG HTTP 客户端 + rag_query 改造 | 3-4 天 | `src/kivi_agent/core/rag/` 新模块 + rag_query Tool 改 Adapter |
| F2 | 数据库 Adapter 架构（Postgres / SQLite / Mock） | 3-4 天 | `src/kivi_agent/core/db/` Protocol + 3 Adapter + query_database 改 Adapter |
| F3 | 配置系统 + 健康检查 + 切换机制 | 2-3 天 | `src/kivi_agent/core/config_runtime.py` + 健康检查 + 降级日志 |
| F4 | 本地 rag-kb mock server + E2E 集成 | 2-3 天 | `tests/e2e_real/` + docker-compose for test DB |
| F5 | 集成 + 文档 + 演示 | 2-3 天 | `integration/aigroup-wave4` 分支 → main |

**总估时**：12-17 天，4 WT 并行 + 集成

### 2.2 明确不做（推迟到 Wave 5+）

| 项 | 推迟理由 | 后续 |
|---|---|---|
| 真实生产数据库（用户权限 / 数据源未明确） | 用户决定 | Wave 5+ |
| 真实云服务 / Key（Tavily / RAGFlow Cloud） | 用户决定 | Wave 5+ |
| VectorMemoryBackend 真实实现 | Wave 5 范围 | Wave 5 |
| Eval T11/T12 + Dashboard | Wave 5/6 范围 | Wave 5/6 |
| Web Chat 深化（登录 / 租户） | Wave 7 范围 | Wave 7 |

---

## 三、4 个 WT 拆分

### WT-F1 RAG HTTP 客户端 + rag_query 改造

**目标**：通过 HTTP API 调用本地 rag-kb，可降级到 Mock。

**任务**：
- `src/kivi_agent/core/rag/client.py`：RagKbClient 类（httpx.AsyncClient 封装）
  - `search(query: str, kb_id: str | None) -> RagSearchResult`
  - `health_check() -> bool`
  - `close()`：清理连接
- `src/kivi_agent/core/rag/types.py`：RagSearchResult / RagSource 数据类（与 v1 §1 6 业务 Tool 解耦）
- `src/kivi_agent/core/business/rag_query.py`：RagQueryTool 改造
  - 构造时接收 `RagKbClient | None`（None = 走 Mock）
  - 真实模式：调 `client.search()` → 格式化 → 返回
  - Mock 模式：保留现有 `_mock_retrieval` 逻辑
  - 失败时降级到 Mock + 记 warn 日志
- 配置：`RAG_MODE=mock|http`，`RAG_API_URL=http://localhost:8001`
- 单元 + 集成测试

**交付文件**：
- `src/kivi_agent/core/rag/__init__.py`（新）
- `src/kivi_agent/core/rag/client.py`（新，~120 行）
- `src/kivi_agent/core/rag/types.py`（新，~60 行）
- `src/kivi_agent/core/business/rag_query.py`（改造 +30 行）
- `tests/unit/test_rag_client.py`（新，~150 行，6+ 测试）
- `tests/integration/test_rag_query_real_vs_mock.py`（新，~100 行，3 场景）

### WT-F2 数据库 Adapter 架构

**目标**：DatabaseAdapter Protocol + Postgres / SQLite / Mock Adapter + query_database 改 Adapter。

**任务**：
- `src/kivi_agent/core/db/__init__.py`：DatabaseAdapter Protocol
  ```python
  class DatabaseAdapter(Protocol):
      async def execute(self, sql: str, params: dict | None = None) -> list[dict]: ...
      async def health_check(self) -> bool: ...
      async def close(self) -> None: ...
  ```
- `src/kivi_agent/core/db/mock_adapter.py`：MockAdapter（保留现有 LocalMemoryBackend 逻辑）
- `src/kivi_agent/core/db/sqlite_adapter.py`：SQLiteAdapter（用 aiosqlite）
- `src/kivi_agent/core/db/postgres_adapter.py`：PostgresAdapter（用 asyncpg，**默认走 SQLite 或 Mock，Postgres 仅作 fallback**）
- `src/kivi_agent/core/business/query_database.py`：QueryDatabaseTool 改造
  - 构造时接收 `DatabaseAdapter`
  - 真实模式：调 `adapter.execute(sql, params)` → 格式化 → 返回
  - 失败时降级到 Mock + 记 warn 日志
- 配置：`DB_MODE=mock|sqlite|postgres`，`DATABASE_URL=sqlite:///path/to.db` 或 `postgresql://user:pass@host:port/db`
- 单元 + 集成测试（sqlite 真跑，postgres 用 testcontainers 或跳过）

**交付文件**：
- `src/kivi_agent/core/db/__init__.py`（新，Protocol 定义）
- `src/kivi_agent/core/db/mock_adapter.py`（新，~80 行）
- `src/kivi_agent/core/db/sqlite_adapter.py`（新，~120 行）
- `src/kivi_agent/core/db/postgres_adapter.py`（新，~120 行）
- `src/kivi_agent/core/business/query_database.py`（改造 +40 行）
- `tests/unit/test_db_adapters.py`（新，~200 行，8+ 测试）
- `tests/integration/test_query_database_real_vs_mock.py`（新，~120 行，3 场景）

### WT-F3 配置系统 + 健康检查 + 切换机制

**目标**：环境变量 + TOML 配置 + 启动时健康检查 + 失败自动降级。

**任务**：
- `src/kivi_agent/core/config_runtime.py`：ConfigRuntime 类
  - 加载顺序：环境变量 > TOML 配置文件 > 默认值
  - 配置项：`RAG_MODE` / `RAG_API_URL` / `RAG_TIMEOUT` / `DB_MODE` / `DATABASE_URL` / `HEALTH_CHECK_INTERVAL`
- 健康检查器：
  - 启动时对每个真实服务做 health_check
  - 失败时自动降级到 Mock + 记 warn 日志
  - 定期重试（每 60s）
- 暴露端点：`GET /health/detailed` 返回每个 Adapter 的健康状态
- 配置文件示例：`config.example.toml`（含所有可配置项 + 注释）
- 单元测试

**交付文件**：
- `src/kivi_agent/core/config_runtime.py`（新，~150 行）
- `src/kivi_agent/gateway/health.py`（新，~80 行，健康检查端点）
- `config.example.toml`（新，~60 行）
- `tests/unit/test_config_runtime.py`（新，~150 行，8+ 测试）
- `tests/unit/test_health_checker.py`（新，~120 行，5+ 测试）

### WT-F4 本地 rag-kb mock server + E2E 集成

**目标**：用 FastAPI in-process 模拟 rag-kb 服务 + Docker 测试 DB + E2E 跑通真实接入路径。

**任务**：
- `tests/fixtures/rag_kb_mock_server.py`：FastAPI 模拟 rag-kb 服务
  - `POST /api/v1/search`：返回 mock sources
  - `GET /health`：健康检查
  - in-process 启动 + 随机端口
- `docker-compose.test.yml`：Postgres 测试 DB
  - 固定种子数据（`init.sql`）
  - 用户：`test` / 密码：`test` / DB：`kivi_test`
- E2E 场景：
  - 真实模式：启动 mock rag-kb + Postgres → 验证 rag_query / query_database 走真实路径
  - 降级模式：杀掉 mock rag-kb → 验证自动降级到 Mock + 业务继续
  - 配置模式：通过环境变量切换 RAG_MODE=http ↔ mock
- E2E 文档：复现步骤 + 故障排查

**交付文件**：
- `tests/fixtures/rag_kb_mock_server.py`（新，~150 行）
- `docker-compose.test.yml`（新，~30 行）
- `tests/sql/init.sql`（新，~50 行）
- `tests/e2e_real/test_rag_real.py`（新，~200 行，4 场景）
- `tests/e2e_real/test_db_real.py`（新，~200 行，4 场景）
- `tests/e2e_real/test_fallback.py`（新，~150 行，3 场景）
- `tests/e2e_real/README.md`（新，~80 行）

---

## 四、目录结构

### 新增

```
src/kivi_agent/core/rag/                # WT-F1 全部新增
  __init__.py
  client.py
  types.py

src/kivi_agent/core/db/                 # WT-F2 全部新增
  __init__.py          # DatabaseAdapter Protocol
  mock_adapter.py
  sqlite_adapter.py
  postgres_adapter.py

src/kivi_agent/gateway/health.py        # WT-F3 新增（健康检查端点）
config.example.toml                    # WT-F3 新增

tests/fixtures/rag_kb_mock_server.py    # WT-F4 新增
docker-compose.test.yml                # WT-F4 新增
tests/sql/init.sql                      # WT-F4 新增
tests/e2e_real/                         # WT-F4 全部新增
  __init__.py
  test_rag_real.py
  test_db_real.py
  test_fallback.py
  README.md
```

### 修改

```
src/kivi_agent/core/business/rag_query.py        # WT-F1 改造（接 RagKbClient）
src/kivi_agent/core/business/query_database.py   # WT-F2 改造（接 DatabaseAdapter）
src/kivi_agent/core/memory/loader.py             # WT-F3 微调（注入 ConfigRuntime）
src/kivi_agent/gateway/main.py                   # WT-F3 注册 /health/detailed 端点
pyproject.toml                                   # 加 httpx / asyncpg / aiosqlite / testcontainers dev 依赖
docs/迁移记录/最小闭环验收记录.md                  # 新增 Wave 4 章节
```

---

## 五、Wave 4 实施流程

按 Wave 1/2/3 成熟模式：

1. **4 个 worktree 并行**（`integration/aigroup-wave4-{rag,db,config,e2e}`）
2. **4 个 sub-agent 并行**（每个 3-4 天工作量）
3. **主控集成**：
   - 建 `integration/aigroup-wave4` 分支
   - 顺序 merge 4 个 WT
   - 处理冲突
   - 跑全量测试
   - 修 ruff
   - 写文档
   - 推 origin
4. **关闭判定**（见 §七）

---

## 六、风险与缓解

| 风险 | 缓解 |
|---|---|
| rag-kb API schema 未明确（不在本仓库） | 子 agent 按 REST 惯例设计 + 写详细 API 假设文档（待用户 / rag-kb 维护方 review） |
| Postgres Docker 依赖（E2E 需要 Docker） | 用 testcontainers-python 自动管理；若无 Docker 则跳过 Postgres E2E 只测 SQLite |
| 真实接入可能性能/稳定性差 | 启动时 health_check + 失败降级 + 定期重试（WT-F3） |
| Adapter 协议抽象泄漏 | Protocol 严格定义 + Mock / SQLite / Postgres 三实现对齐 |
| 与 v1 §7.2 demo 定位张力 | 保留 Mock 为默认；真实服务需显式 `RAG_MODE=http` / `DB_MODE=sqlite` 才启用 |

---

## 七、Wave 4 关闭判定

- [ ] 4 个子包全部合入 `integration/aigroup-wave4` → `main`
- [ ] 后端测试 952+N passed / 0 failed（N 待统计）
- [ ] 前端 55 测试不受影响
- [ ] mypy 0 issue（后端新增 RAG / DB / config / health 模块）
- [ ] ruff 0 新增
- [ ] RAG 客户端：mock + http 两种模式 + 降级
- [ ] DB Adapter：mock + sqlite + postgres（postgres 可选 testcontainers）三种实现
- [ ] 配置系统：环境变量 + TOML + 启动时健康检查 + 失败降级
- [ ] `/health/detailed` 端点：返回每个 Adapter 状态
- [ ] E2E 4+ 场景：真实模式 / 降级模式 / 配置切换
- [ ] Docker test DB：固定种子数据可复现
- [ ] 文档同步：最小闭环验收记录新增 Wave 4 章节
- [ ] v1 契约未变（无新增 Tool 名 / 事件 / 字段）
- [ ] WIRE_PROTOCOL.md 同步

---

## 八、Wave 5+ 候选

| Wave | 内容 | 估时 |
|---|---|---|
| Wave 5 | Vector Memory Backend 真实实现 + Eval T11/T12 | 30+ 天 |
| Wave 6 | 完整 Evaluation Dashboard | 30+ 天 |
| Wave 7 | Web Chat 深化（登录 / 租户 / 多用户） | 30+ 天 |

---

## 九、参考

- 方案：`kivi-agent与aigroup整合实施方案.md` §5 阶段 5/6
- v1 契约：`docs/contracts/v1.md`（不变）
- Wave 3 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 3" 章节
- Wave 1 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 1" 章节
- 现状：
  - `src/kivi_agent/core/business/rag_query.py`（明确注释"未来切真 RAGFlow"）
  - `src/kivi_agent/core/memory/loader.py`（LocalMemoryBackend）
  - `src/kivi_agent/gateway/main.py`（注册健康检查端点）

---

**Wave 4 起草**：Mavis（主控 Agent）
**用户批准**：2026-07-23 "选 B 真实 RAG/DB 接入 + 选 A 本地 Docker 替代 + 多 worktree 并行"
**下一步**：创建 4 个 worktree + 启动 4 个 sub-agent（WT-F1/F2/F3/F4 并行）
