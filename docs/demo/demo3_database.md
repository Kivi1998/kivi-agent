# Demo 3：数据库 Agent（自然语言问数）

> **能力**：自然语言 → SQL → 执行 → 表格 + 图表（ECharts 元数据）。
> **Wave 来源**：Wave 4 F2（DatabaseAdapter + Mock / SQLite / Postgres）+ Wave 4 F3（健康检查 + 配置）。
> **Web 端查看**：Chat 页面 + ChartWidget（ECharts 真画图）。

## 1. 演示目标

让用户看到 kivi-agent 能**用自然语言问数据库 + 生成图表元数据**，并演示：

- Mock 模式：内存表（演示用，零依赖）
- SQLite 模式：真实本地文件
- Postgres 模式：真实 Docker Postgres（WT-F4 已做 E2E）

## 2. 输入

### 2.1 Fixture

`demos/fixtures/demo3_database_fixture.sql`（orders 表 + 100 行种子数据）：

```sql
-- 订单表（100 行种子数据）
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

-- 插入 100 行（10 个客户 × 10 个状态）
-- 这里省略具体 INSERT，WT-K2 交付时包含完整 fixture
```

### 2.2 Spec（用户输入）

```
统计每个客户的订单总金额，按金额降序排列，前 5 名
```

或（生成图表）：

```
画一个订单状态分布的饼图
```

### 2.3 配置

`config.toml` 或 `.env`：

```toml
[db]
mode = "mock"                                  # 默认 Mock（内存表）
# mode = "sqlite"                              # 真实 SQLite
# database_url = "sqlite:///~/.kivi/kivi.db"
# mode = "postgres"                            # 真实 Postgres（需 Docker）
# database_url = "postgresql://kivi_test:kivi_test@localhost:5432/kivi_test"
```

或 `.env`：

```bash
# DB_MODE=sqlite
# DB_DATABASE_URL=sqlite:///~/.kivi/kivi.db
```

## 3. 期望输出

### 3.1 命令行输出（Mock 模式）

```
$ uv run python -m demos.demo3_database

=== Demo 3: 数据库 Agent（自然语言问数）===

[Step 1] 接收任务：统计每个客户的订单总金额，按金额降序排列，前 5 名
[Step 2] BusinessRouter 路由 → [database]（命中"统计""金额"关键词）
[Step 3] database Profile 执行
        - LLM 生成 SQL：
          SELECT customer_id, SUM(amount) AS total
          FROM orders
          GROUP BY customer_id
          ORDER BY total DESC
          LIMIT 5;
        - 调用 query_database(sql=...)
        - 走 MockAdapter，返回 5 行
[Step 4] database Profile 整理成表格 + 图表元数据

=== 回答（表格）===

| customer_id | total    |
|-------------|----------|
| 1           | 12345.67 |
| 2           | 10234.56 |
| 3           | 9876.54  |
| 4           | 8765.43  |
| 5           | 7654.32  |

=== 图表元数据 ===

{
  "chart_id": "bar-001",
  "option_dict": {
    "title": {"text": "Top 5 客户订单总金额"},
    "xAxis": {"type": "category", "data": ["1", "2", "3", "4", "5"]},
    "yAxis": {"type": "value"},
    "series": [{"type": "bar", "data": [12345.67, 10234.56, 9876.54, 8765.43, 7654.32]}]
  }
}

=== T11/T12 + DB 指标 ===

query_success: true
rows_returned: 5
sql_generation_correct: true
chart_generated: true

=== Demo 3 状态：PASS（耗时 2.4s）===
```

### 3.2 SQLite 模式输出

```
[Step 3] database Profile 执行
        - LLM 生成 SQL：...
        - 调用 query_database(sql=...)
        - 走 SQLiteAdapter，连接 ~/.kivi/kivi.db
        - 返回 5 行（来自 fixture 种子数据）
```

### 3.3 截图位

<!-- screenshot -->

> 截图位置：Web Chat → 问"统计客户订单总金额" → 看到 Chat 表格 + ChartWidget 渲染的柱状图。

### 3.4 Web Dashboard 显示

- **Chat 页面**：表格（HTML table）+ ChartWidget（ECharts 真画图）
- **ChartWidget**：vue-echarts `shallowMount` 渲染柱状图 / 饼图

## 4. 复现命令

### 4.1 跑单个 demo

```bash
# 1. 启 Core Daemon
uv run kivi-core &

# 2. 跑 demo
uv run python -m demos.demo3_database
# → 应看到 "Demo 3 状态：PASS"
# → 应看到表格 + 图表元数据
```

### 4.2 切到 SQLite 模式

```bash
# 1. 初始化 SQLite 数据库
mkdir -p ~/.kivi
sqlite3 ~/.kivi/kivi.db < demos/fixtures/demo3_database_fixture.sql

# 2. 配 .env
echo "DB_MODE=sqlite" >> .env
echo "DB_DATABASE_URL=sqlite:///$HOME/.kivi/kivi.db" >> .env

# 3. 重启 Core
kill $(pgrep -f kivi-core)
uv run kivi-core &

# 4. 跑 demo
uv run python -m demos.demo3_database
```

### 4.3 切到 Postgres 模式

```bash
# 1. 起 Postgres 测试容器
docker-compose -f docker-compose.test.yml up -d
sleep 5

# 2. 配 .env
echo "DB_MODE=postgres" >> .env
echo "DB_DATABASE_URL=postgresql://kivi_test:kivi_test@localhost:5432/kivi_test" >> .env

# 3. 重启 Core
kill $(pgrep -f kivi-core)
uv run kivi-core &

# 4. 跑 demo
uv run python -m demos.demo3_database
```

### 4.4 Web 端查看

```bash
# 1. 启 Gateway
uv run kivi-gateway &

# 2. 启前端
cd apps/web-chat && npm run dev

# 3. 浏览器访问 http://localhost:5173/chat
# 4. 输入"统计每个客户的订单总金额"
# → 看到 Chat 表格 + ChartWidget 柱状图
```

## 5. 故障排查

### 5.1 SQL 生成错误

**症状**：

```
query_database failed: no such table: orders
```

**排查**：

```bash
# 1. 确认 fixture 已加载
sqlite3 ~/.kivi/kivi.db ".tables"
# → 应有 orders 表

# 2. 看 SQL 是不是错了
# LLM 生成的 SQL 在 EvalResult.events 里能看到
curl -fsS http://127.0.0.1:8000/api/dashboard/runs | jq '.[].events[] | select(.type=="tool.call_started") | .data.input.sql'
```

**修复**：

- 加载 fixture：`sqlite3 ~/.kivi/kivi.db < demos/fixtures/demo3_database_fixture.sql`
- 或重跑 demo 让 LLM 重新生成 SQL

### 5.2 路径遍历被拒

**症状**：

```
ValueError: invalid database path: ../../../etc/passwd
```

**原因**：`SQLiteAdapter` 拒绝 `..` 路径（防御）。

**修复**：

- 用绝对路径或 `~` 开头
- 检查 `core/db/sqlite.py` 的 `_ensure_safe_path` 逻辑

### 5.3 图表没渲染

**症状**：表格显示但 ChartWidget 空白。

**排查**：

```bash
# 1. 看是否有 ChartRenderedEvent
curl -fsS http://127.0.0.1:8000/api/dashboard/runs | jq '.[].events[] | select(.type=="chart.rendered")'

# 2. 看前端 console
# Chrome DevTools → Console → 看 ResizeObserver 错误（如果缺桩）
```

**修复**：

- 确认 `core/business/echarts_render.py` 触发了 `ChartRenderedEvent`
- 确认 `apps/web-chat/src/test-setup.ts` 桩了 `ResizeObserver`
- 确认 vue-echarts `shallowMount` 正确

### 5.4 Postgres 模式连不上

**症状**：

```
asyncpg.exceptions.CannotConnectNowError
```

**排查**：

```bash
# 1. 看 Postgres 容器
docker-compose -f docker-compose.test.yml ps

# 2. 测连接
psql postgresql://kivi_test:kivi_test@localhost:5432/kivi_test -c "SELECT 1"
```

**修复**：

- 起 Postgres：`docker-compose -f docker-compose.test.yml up -d`
- 等 5-10 秒等 Postgres 初始化
- 检查端口 `lsof -i :5432`

## 6. 数据流

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant Demo as demo3_database.py
    participant Router as BusinessRouter
    participant Profile as database Profile
    participant LLM as LLM
    participant Tool as query_database Tool
    participant Adapter as DatabaseAdapter
    participant DB as 数据库
    participant Bus as EventBus

    U->>Demo: "统计每个客户的订单总金额"
    Demo->>Router: route(query)
    Router-->>Demo: RouteDecision(target_profiles=[database])
    Demo->>Profile: 启动 database subagent
    Profile->>LLM: prompt=question, tools=[query_database, echarts_render]
    LLM-->>Profile: tool_use(query_database, sql="SELECT...")
    Profile->>Tool: query_database(sql="SELECT...")
    alt DB_MODE=mock
        Tool->>Adapter: MockAdapter
        Adapter-->>Tool: 5 行
    else DB_MODE=sqlite
        Tool->>Adapter: SQLiteAdapter
        Adapter->>DB: ~/.kivi/kivi.db
        DB-->>Adapter: 5 行
    else DB_MODE=postgres
        Tool->>Adapter: PostgresAdapter
        Adapter->>DB: localhost:5432
        DB-->>Adapter: 5 行
    end
    Tool-->>Profile: list[dict]
    Profile->>Tool: echarts_render(type="bar", data=...)
    Tool-->>Bus: emit ChartRenderedEvent
    Bus-->>Profile: 事件
    Profile-->>Demo: 表格 + 图表元数据
    Demo-->>U: 终端显示
```

## 7. 关键文件

| 文件 | 说明 |
|---|---|
| `demos/demo3_database.py` | 演示脚本（WT-K2 交付） |
| `demos/fixtures/demo3_database_fixture.sql` | orders 表 + 种子数据 |
| `src/kivi_agent/core/db/__init__.py` | `DatabaseAdapter` Protocol |
| `src/kivi_agent/core/db/mock.py` | `MockAdapter`（内存表） |
| `src/kivi_agent/core/db/sqlite.py` | `SQLiteAdapter`（aiosqlite） |
| `src/kivi_agent/core/db/postgres.py` | `PostgresAdapter`（asyncpg） |
| `src/kivi_agent/core/business/query_database.py` | `QueryDatabaseTool` |
| `src/kivi_agent/core/business/echarts_render.py` | `EChartsRenderTool`（返回 option_dict） |
| `config.example.toml [db]` 段 | DB 配置 |
| `docker-compose.test.yml` | Postgres 测试容器 |
| `apps/web-chat/src/components/ChartWidget.vue` | ECharts 真画图 |

## 8. 验收标准

- [ ] Mock 模式跑过：`Demo 3 状态：PASS`
- [ ] SQL 生成正确（执行无错）
- [ ] 表格显示
- [ ] 图表元数据生成（ChartRenderedEvent 触发）
- [ ] SQLite 模式：fixture 加载 + 查询成功
- [ ] Web 端：ChartWidget 渲染（ECharts 真画图）

## 9. 后续阅读

- [demo1_coding.md](demo1_coding.md)：编程 Agent
- [demo2_rag.md](demo2_rag.md)：知识库 Agent
- [demo4_frontend_map.md](demo4_frontend_map.md)：前端操作 Agent
- [demo5_multi_agent.md](demo5_multi_agent.md)：综合多 Agent
- [../architecture/architecture.md §4.8](../architecture/architecture.md)：core/db/ 模块说明
