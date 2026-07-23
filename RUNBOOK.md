# 运维手册（RUNBOOK）

> kivi-agent 完整操作参考：配置详解、启停操作、开发命令、故障排查、监控日志、升级迁移。
> README 是项目入口，本文档是**操作手册**——遇到具体问题来这里查。

## 目录

1. [配置详解](#1-配置详解)
2. [启停操作](#2-启停操作)
3. [开发命令](#3-开发命令)
4. [故障排查（7 场景）](#4-故障排查7-场景)
5. [监控 / 日志](#5-监控--日志)
6. [升级 / 迁移指南](#6-升级--迁移指南)

---

## 1. 配置详解

配置优先级（低 → 高）：**内建默认值 → `~/.kivi/config.toml` → `.env` → 系统环境变量**。

### 1.1 配置文件路径

| 路径 | 用途 |
|---|---|
| `.env.example` | 仓库根目录的**配置模板**（含所有变量说明 + 默认值，不含真值） |
| `.env` | 本机配置（不提交 git；按需从 `.env.example` 复制） |
| `config.example.toml` | TOML 格式配置（用于 RAG/DB/Embedding/ES 等结构化配置） |
| `~/.kivi/config.toml` | 全局配置（所有项目共用） |
| `~/.kivi/logs/` | 日志目录（自动创建） |

### 1.2 `.env.example` 完整变量清单

> **复制命令**：`cp .env.example .env`，然后按需取消注释 / 修改。

#### Core Daemon

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KAMA_HOST` | `127.0.0.1` | TCP 监听地址（loopback 即可；外部访问需 `0.0.0.0`） |
| `KAMA_PORT` | `7437` | TCP 监听端口 |
| `KAMA_LOG_LEVEL` | `INFO` | 日志级别（`DEBUG` / `INFO` / `WARNING` / `ERROR`） |
| `KAMA_LOG_FILE` | `~/.kivi/logs/core.log` | 日志文件路径（留空则仅输出 stderr） |
| `KAMA_LOG_FORMAT` | `text` | 日志格式（`text` 人工可读 / `json` 结构化） |
| `KAMA_CONFIG` | `~/.kivi/config.toml` | 覆盖配置文件路径 |

#### LLM（Wave 1+ 启用）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API Key（**必填**，不设则 LLM 调用失败） |
| `KAMA_LLM_DEFAULT_MODEL` | `claude-sonnet-4-6` | 默认模型名 |
| `KAMA_MAX_STEPS` | `20` | 单次 Run 最大步数（防止 LLM 死循环） |
| `ANTHROPIC_BASE_URL` | — | Anthropic 兼容端点（DeepSeek / Moonshot 等）；`anthropic` SDK 原生支持 |

#### OpenAI 兼容 Embedding（Wave 6.1+）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI Embedding API Key（与 `ANTHROPIC_API_KEY` 可共用） |
| `OPENAI_BASE_URL` | — | OpenAI 兼容端点（也可走 `ANTHROPIC_BASE_URL` 兼容） |

#### Vector Memory（Wave 6.1+ 启用）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KIVI_MEMORY_BACKEND` | `local` | `local`（Markdown 文件）/ `vector`（ES 向量检索） |
| `KIVI_EMBEDDING_PROVIDER` | `fake` | `fake`（SHA-512 伪随机）/ `openai`（真实 Embedding） |
| `KIVI_EMBEDDING_DIMS` | `384` | 向量维度（与 ES 索引 mapping 强一致） |
| `KIVI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding 模型名 |
| `KIVI_ES_URL` | `http://localhost:9200` | ES 服务地址 |
| `KIVI_ES_INDEX` | `kivi-memories` | 向量索引名 |
| `KIVI_ES_AUDIT_INDEX` | `kivi-memory-audit` | 审计事件索引 |
| `KIVI_ES_TIMEOUT_S` | `5.0` | ES 请求超时（秒） |
| `KIVI_MEMORY_AUTO_FALLBACK` | `true` | 真实服务不可用时是否自动降级到 Local |

#### Health Check（Wave 4+ 启用）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KIVI_HEALTH_INTERVAL_S` | `60.0` | 健康检查间隔（秒） |
| `KIVI_HEALTH_TIMEOUT_S` | `3.0` | 单次健康检查超时（秒） |

#### Gateway（Wave 3+ 启用）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `KIVI_GATEWAY_HOST` | `127.0.0.1` | Gateway 监听地址 |
| `KIVI_GATEWAY_PORT` | `8000` | Gateway 监听端口 |
| `KIVI_GATEWORK_CORS_ORIGINS` | `http://localhost:5173` | 允许跨域来源（逗号分隔） |

### 1.3 `config.example.toml` 结构化配置

按 section 分组，适合复杂结构（RAG / DB / Embedding / ES / Pricing / Memory / Health）：

```toml
# 顶层 key：真实服务不可用时是否自动降级到 Mock
auto_fallback = true

[rag]
mode = "mock"                  # mock / http
api_url = "http://localhost:8001"
timeout_s = 5.0

[db]
mode = "mock"                  # mock / sqlite / postgres
database_url = "sqlite:///~/.kivi/kivi.db"

[memory]
backend = "local"              # local / vector

[embedding]
provider = "fake"              # fake / openai
dims = 384
model = "text-embedding-3-small"

[es]
url = "http://localhost:9200"
index = "kivi-memories"
audit_index = "kivi-memory-audit"
timeout_s = 5.0

[health]
interval_s = 60.0
timeout_s = 3.0

[pricing]
"claude-sonnet-4-6" = [0.003, 0.015]   # [input_per_1k, output_per_1k] USD
```

详细字段含义见 `config.example.toml` 内注释（每个字段都有说明 + 取值范围）。

### 1.4 LLM Provider 切换

**核心结论**：daemon 不需要改任何代码即可切换 Anthropic 兼容端点。

| 场景 | 配置 |
|---|---|
| 真实 Anthropic（默认） | `ANTHROPIC_API_KEY=sk-...`（不设 `ANTHROPIC_BASE_URL`） |
| DeepSeek / Moonshot 等 | `ANTHROPIC_API_KEY=sk-...` + `ANTHROPIC_BASE_URL=https://<host>/anthropic` |
| 模型名 | `KAMA_LLM_DEFAULT_MODEL=deepseek-v4-pro` |
| OpenAI 协议路径 | `llm.provider=openai_compat`（走 `/v1/chat/completions`） |

---

## 2. 启停操作

### 2.1 minimal 模式（仅 Core + CLI/TUI）

**启动**：

```bash
# 终端 1：后台启动 Core Daemon
uv run kivi-core &

# 等待 2 秒让 daemon 初始化
sleep 2

# 终端 2：验证连通
uv run kivi ping
# → pong server=0.0.1 uptime=12ms latency=2ms

# 查看版本
uv run kivi --version
# → 0.0.1

# 启动 TUI
uv run kivi-tui
```

**健康检查**：

```bash
# Daemon 自带健康端点（如果有）；或用 ping 协议
uv run kivi ping
```

**停止**：

```bash
# 优雅停止
kill $(pgrep -f kivi-core)

# 强制停止（如果优雅停不下来）
kill -9 $(pgrep -f kivi-core)
```

### 2.2 web 模式（Core + Gateway + Web Chat）

**启动**（3 终端）：

```bash
# 终端 1：Core Daemon
uv run kivi-core &

# 终端 2：FastAPI Gateway（默认 8000）
uv run kivi-gateway

# 终端 3：Vue 3 前端开发服务器（默认 5173）
cd apps/web-chat && npm install && npm run dev
```

**健康检查**：

```bash
# Core ping
uv run kivi ping

# Gateway 简单健康
curl -fsS http://127.0.0.1:8000/health
# → {"status":"ok","daemon":"connected"}

# Gateway 详细健康（207 Multi-Status）
curl -fsS http://127.0.0.1:8000/health/detailed | jq
# → { "daemon": "ok", "rag": "mock|degraded", "db": "ok|fallback_to_mock", "memory": "local|vector" }

# 前端代理到 Gateway（验证反向代理）
curl -fsS http://127.0.0.1:5173/api/dashboard/summary | jq '.total_runs'
```

**停止**：

```bash
# Gateway（uvicorn 自带 Ctrl+C；如用 & 启动则 kill）
kill $(pgrep -f kivi-gateway)

# 前端（vite dev server）
kill $(pgrep -f "vite")
```

### 2.3 full 模式（+ ES + Eval）

**启动**（4 终端 + 1 docker）：

```bash
# 1. 起 Elasticsearch
docker-compose up -d

# 2. 等 ES 起来（首次启动 30~60 秒）
curl -fsS http://localhost:9200/_cluster/health | jq '.status'
# → "green" 或 "yellow"

# 3. Core Daemon（启用 vector memory）
KIVI_MEMORY_BACKEND=vector uv run kivi-core &

# 4. Gateway
uv run kivi-gateway

# 5. 前端
cd apps/web-chat && npm run dev

# 6. 跑 5 演示（端到端）
uv run python -m demos.run_all
```

**健康检查**：

```bash
# ES 集群健康
curl -fsS http://localhost:9200/_cluster/health

# Memory API（Gateway 透传到 ES）
curl -fsS 'http://127.0.0.1:8000/api/memory/search?query=hello' | jq

# Eval Dashboard
curl -fsS 'http://127.0.0.1:8000/api/dashboard/runs' | jq
```

**停止**：

```bash
# 停 Core / Gateway / 前端（同 web 模式）
kill $(pgrep -f kivi-core) $(pgrep -f kivi-gateway) $(pgrep -f "vite")

# 停 ES（保留数据卷）
docker-compose down

# 停 ES + 删除数据卷
docker-compose down -v
```

### 2.4 一键脚本（Wave 7 集成期，WT-K1 交付）

```bash
# 启动（按模式）
./scripts/start.sh --mode minimal
./scripts/start.sh --mode web
./scripts/start.sh --mode full

# 健康检查
./scripts/health_check.sh --mode minimal
./scripts/health_check.sh --mode web
./scripts/health_check.sh --mode full

# 停止
./scripts/stop.sh

# 跑 5 演示
./scripts/run_demos.sh
```

> 注：脚本是 WT-K1 产物，本 RUNBOOK 当前 wave 内为手解；脚本交付后取代上述多终端命令。

---

## 3. 开发命令

### 3.1 Python 依赖

```bash
uv sync                              # 装所有依赖（含 dev）
uv sync --frozen                     # 严格按 uv.lock 装（CI 用）
uv add <pkg>                         # 加运行时依赖
uv add --dev <pkg>                   # 加开发依赖
```

### 3.2 测试

```bash
# 单元测试（不需要 daemon）
uv run pytest tests/unit -v
uv run pytest tests/unit -q          # 静默模式

# 集成测试
uv run pytest tests/integration -v

# E2E 测试（需要真实服务）
uv run pytest tests/e2e -v

# 全量
uv run pytest -v

# 跑指定文件 / 用例
uv run pytest tests/unit/test_memory.py -v
uv run pytest tests/unit/test_memory.py::test_vector_search -v

# 按 marker 过滤
uv run pytest -m "not integration" -v
```

### 3.3 类型检查

```bash
uv run mypy src                      # 全量
uv run mypy src/kivi_agent/core/memory  # 单包
```

### 3.4 Lint

```bash
uv run ruff check src tests scripts  # 全量
uv run ruff check src/kivi_agent/core/memory  # 单包
uv run ruff check --fix src tests    # 自动修复
```

### 3.5 协议文档

```bash
# 重新生成 WIRE_PROTOCOL.md（修改 bus/events.py 或 bus/commands.py 后必跑）
uv run python scripts/gen_protocol_doc.py

# 验证协议文档与代码同步（CI 用）
uv run python scripts/gen_protocol_doc.py --check
```

### 3.6 前端（apps/web-chat）

```bash
cd apps/web-chat

npm install                          # 装依赖
npm run dev                          # 启动 dev server（5173）
npm run build                        # 生产构建（dist/）
npm run type-check                   # vue-tsc 严格模式
npm run lint                         # eslint
npm test                             # vitest
npm run test:coverage                # 覆盖率
```

### 3.7 Makefile 快捷命令

```bash
make lint                            # ruff + mypy
make test                            # 单元测试
make integration-test                # 集成测试
make docs                            # 生成协议文档
make verify-s0                       # 完整验证（lint + 类型 + 测试 + 协议）
```

---

## 4. 故障排查（7 场景）

### 场景 1：API Key 错（`ANTHROPIC_API_KEY invalid`）

**症状**：

```
anthropic.APIError: Could not resolve authentication
```

或

```
llm.call_failed: 401 Unauthorized
```

**排查**：

```bash
# 1. 确认环境变量已设
echo $ANTHROPIC_API_KEY | head -c 10
# → sk-ant-... （前缀对了才是合法 key）

# 2. 用 curl 直接测
curl -fsS https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

**修复**：

- 重新从 Anthropic Console 复制 key
- 确认 key 没用错（开发用 sk-ant-...）
- 如使用 DeepSeek / Moonshot，确认 `ANTHROPIC_BASE_URL` 配对

**预防**：

- `.env` 不提交 git（已配 `.gitignore`）
- 凭据清理（WT-K1 已做 git filter-repo 验证）

### 场景 2：Elasticsearch 起不来（`connection refused 9200`）

**症状**：

```
elasticsearch.ConnectionError: ConnectionError: localhost:9200
```

或 `docker-compose ps` 显示 `kivi-agent-es` 状态 `Exit 1`。

**排查**：

```bash
# 1. 看 ES 容器日志
docker-compose logs elasticsearch | tail -50

# 2. 看端口占用
lsof -i :9200

# 3. 看内存（ES 8.x 需要 ≥ 1GB heap）
docker stats kivi-agent-es

# 4. 单独 curl 测
curl -v http://localhost:9200/_cluster/health
```

**常见原因**：

- **内存不足**：ES 8.x 默认要 1GB heap，本机内存 < 4GB 会 OOM → 改 `docker-compose.yml` 的 `ES_JAVA_OPTS=-Xms512m -Xmx512m`
- **已有 ES 占用 9200**：`lsof -i :9200` 找到 PID，kill 或改 `docker-compose.yml` 端口映射 `"9201:9200"`
- **首次启动慢**：单节点 ES 首次启动要 30~60 秒，看 `start_period: 20s` + 5 次重试

**修复**：

```bash
# 改 docker-compose.yml 后重启
docker-compose down
docker-compose up -d

# 等 30 秒后验证
sleep 30 && curl -fsS http://localhost:9200/_cluster/health
```

**回退**：

如 ES 始终起不来，Memory 走 Local 模式（不依赖 ES）：

```bash
# .env
KIVI_MEMORY_BACKEND=local
```

### 场景 3：Gateway 502 Bad Gateway

**症状**：

```
curl http://127.0.0.1:8000/api/sessions → 502
```

**排查**：

```bash
# 1. Core Daemon 在跑吗？
pgrep -f kivi-core

# 2. Core 健康
uv run kivi ping

# 3. Gateway 日志
journalctl -u kivi-gateway | tail -30  # 或直接看终端输出
```

**常见原因**：

- **Core Daemon 没启** → `uv run kivi-core &`
- **端口冲突**：Gateway 默认 8000 已被占用 → `KIVI_GATEWAY_PORT=8001 uv run kivi-gateway`
- **Core 端口不匹配**：Core 在 7437，但 Gateway 配错 → 检查 Gateway 配置（`core_daemon_host` / `core_daemon_port`）
- **WebSocket 升级失败**：Nginx 反代时未配 `Upgrade` / `Connection` headers

**修复**：

```bash
# 确认两端端口一致
grep -E "(KAMA_PORT|KIVI_GATEWAY)" .env
# KAMA_PORT=7437
# KIVI_GATEWAY_PORT=8000

# 重启 Gateway
kill $(pgrep -f kivi-gateway)
uv run kivi-gateway
```

### 场景 4：测试 flaky（间歇失败）

**症状**：

```
FAILED tests/integration/test_X.py::test_Y - AssertionError
# 第二次跑又过
```

**常见原因**：

- **端口冲突**：测试用临时端口（8001 / 9090 等），多次跑没清理 → 加 `tmp_path` fixture
- **时序问题**：sleep 不够 → 改用轮询（wait_for condition）
- **环境变量泄漏**：本地 `.env` 影响测试 → 测试用 `monkeypatch.setenv` 隔离
- **daemon 子进程残留**：前一次跑没清理 → 加 `try/finally` 清理

**排查**：

```bash
# 单测反复跑（10 次）
for i in {1..10}; do
  uv run pytest tests/integration/test_X.py::test_Y -q
done

# 留详细日志
uv run pytest tests/integration/test_X.py::test_Y -v -s --log-cli-level=DEBUG
```

**修复**：

- 用 `pytest.fixture(scope="function", autouse=True)` 清理全局状态
- 异步测试加 `pytest.mark.asyncio` + `asyncio_mode = "auto"`（已配）
- 时间断言用 `pytest.approx()` 或 `freezegun`

### 场景 5：端口占用（`Address already in use`）

**症状**：

```
OSError: [Errno 48] Address already in use
```

**排查**：

```bash
# 找占用端口的进程
lsof -i :7437
lsof -i :8000
lsof -i :5173
```

**修复**：

```bash
# 优雅：找到进程，确认是 kivi 自己的，kill
kill <PID>

# 强制：kill -9
kill -9 <PID>

# 改端口
KAMA_PORT=7438 uv run kivi-core
KIVI_GATEWAY_PORT=8001 uv run kivi-gateway
```

**预防**：

- 用 `./scripts/stop.sh` 统一停
- 集成测试用 `tmp_path` + 随机端口

### 场景 6：Docker 容器冲突

**症状**：

```
docker-compose up -d
# ERROR: container name "kivi-agent-es" already in use
```

**排查**：

```bash
# 看所有容器（包括已停的）
docker ps -a | grep kivi-agent

# 看所有相关 volume
docker volume ls | grep kivi-agent
```

**修复**：

```bash
# 方案 1：删容器（保留数据卷）
docker-compose down

# 方案 2：删容器 + 数据卷
docker-compose down -v

# 方案 3：删所有 kivi-agent 容器
docker rm -f kivi-agent-es kivi-agent-pg-test
```

**预防**：

- 用 `./scripts/stop.sh`（WT-K1 交付后）
- 不同项目用不同容器名前缀

### 场景 7：LLM 超时（`httpx.ReadTimeout`）

**症状**：

```
httpx.ReadTimeout: timed out
# 或
llm.call_failed: timeout after 30s
```

**排查**：

```bash
# 1. 直连测
time curl -fsS -m 60 https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'

# 2. 看 Core 日志
tail -50 ~/.kivi/logs/core.log | grep -E "(timeout|llm)"
```

**常见原因**：

- **网络慢**（跨太平洋 / VPN 阻塞）
- **prompt 太大**（cache miss + 巨长 history）
- **provider 限流**（429 Too Many Requests）
- **本地代理干扰**：`http_proxy=127.0.0.1:7897` 拦截 127.0.0.1 → 需加 `NO_PROXY=127.0.0.1,localhost,::1`

**修复**：

```bash
# 加超时配置
# .env
KIVI_LLM_TIMEOUT_S=120.0

# 加重试
KIVI_LLM_MAX_RETRIES=3

# 旁路代理
NO_PROXY=127.0.0.1,localhost,::1
```

---

## 5. 监控 / 日志

### 5.1 日志路径

| 路径 | 内容 |
|---|---|
| `~/.kivi/logs/core.log` | Core Daemon 主日志（text 或 json 格式） |
| `~/.kama/traces/daemon.jsonl` | 事件 trace（`run.started` / `llm.usage` / `tool.call_*` / `run.finished`） |
| `~/.kama/sessions/sess-*/` | 会话历史 + checkpoint |
| `~/.kivi/eval/runs/` | Eval 结果 JSONL |
| `~/.kivi/memory/` | Local 模式长期记忆（Markdown） |
| `~/.kivi/dashboard/` | Dashboard 单例状态（进程内） |
| `~/.kivi/kivi.db` | SQLite 模式数据库 |

### 5.2 实时看日志

```bash
# Core 日志
tail -f ~/.kivi/logs/core.log

# JSON 格式日志（jq 解析）
tail -f ~/.kivi/logs/core.log | jq '.'

# 事件 trace
tail -f ~/.kama/traces/daemon.jsonl | jq '.'

# 按事件类型过滤
tail -f ~/.kama/traces/daemon.jsonl | jq 'select(.type=="tool.call_started")'

# 按 run_id 过滤
tail -f ~/.kama/traces/daemon.jsonl | jq 'select(.run_id=="run-2026-07-23-001")'
```

### 5.3 关键监控指标

通过 Eval Dashboard API 监控（Wave 5.1+）：

```bash
# 7 个核心指标（单 run）
curl -fsS http://127.0.0.1:8000/api/dashboard/metrics/<run_id> | jq
# → {
#     "task_success_rate": 0.9,
#     "route_accuracy": 0.85,
#     "tool_selection_accuracy": 0.92,
#     "rag_citation_accuracy": 0.88,
#     "avg_latency_seconds": 12.4,
#     "total_tokens": 15234,
#     "total_cost_usd": 0.45
#   }

# 汇总
curl -fsS http://127.0.0.1:8000/api/dashboard/summary | jq

# Team 指标（T11）
curl -fsS http://127.0.0.1:8000/api/dashboard/team/<run_id> | jq
# → {
#     "team_success_rate": 0.8,
#     "delegation_accuracy": 0.9,
#     "handoff_quality": 0.85,
#     "coordination_latency_s": 8.2,
#     "agent_utilization": 0.7,
#     "role_consistency": 0.95
#   }

# Coding 指标（T12）
curl -fsS http://127.0.0.1:8000/api/dashboard/coding/<run_id> | jq
```

### 5.4 Memory 监控

```bash
# 看 MemoryItem 数量
curl -fsS http://127.0.0.1:8000/api/memory/list | jq '.total'

# 看审计事件
curl -fsS 'http://127.0.0.1:8000/api/memory/audit?limit=20' | jq

# 搜相关记忆
curl -fsS 'http://127.0.0.1:8000/api/memory/search?query=RAG&top_k=5' | jq
```

### 5.5 健康检查端点

| 端点 | 用途 |
|---|---|
| `uv run kivi ping` | Core TCP loopback 健康 |
| `GET /health` | Gateway 简单健康（daemon 连接） |
| `GET /health/detailed` | Gateway 详细健康（daemon + rag + db + memory + embedding）— 207 Multi-Status |

---

## 6. 升级 / 迁移指南

### 6.1 Wave 间升级

**从 Wave N 升到 Wave N+1**：

```bash
# 1. 拉新代码
git fetch origin
git pull origin main
uv sync                  # 装新依赖

# 2. 更新 .env（Wave N+1 可能加新变量）
diff .env .env.example   # 看新增变量
# 按需复制新变量

# 3. 重新生成协议文档（如 WIRE_PROTOCOL.md 变了）
make docs

# 4. 重启服务
kill $(pgrep -f kivi-core)
uv run kivi-core &

# 5. 跑测试确认不退化
make test
```

**配置向后兼容**：

- 内建默认值保证新变量都有合理 fallback
- 旧 `.env` 不删变量可继续用
- 数据库 schema 升级用 `auto_fallback=true` 兜底

### 6.2 跨大版本升级（Breaking Changes）

不适用——kivi-agent 仍在 0.0.x，v1.0.0 之前无 breaking change 承诺。

### 6.3 从 aigroup / mewcode 迁移（背景）

kivi-agent = KamaClaude 底座 + aigroup 业务能力迁移 + mewcode 44 项能力 + Wave 6.1 Vector Memory。

完整迁移记录见 **[docs/迁移记录/最小闭环验收记录.md](docs/迁移记录/最小闭环验收记录.md)**，覆盖 Wave 1~6.1 共 162 commit、6 个子系统的合并细节。

**已迁移**（详见 [MIGRATION.md](./MIGRATION.md)）：

- aigroup 业务 Tool（6 个，Wave 1）
- aigroup BusinessRouter + 5 Profile（Wave 2）
- aigroup Web Chat（Wave 3）
- aigroup RAG HTTP + DB Adapter（Wave 4）
- aigroup Eval 体系 + Trace Dashboard（Wave 5.1）
- T11 Team 指标 + T12 Coding 指标（Wave 5.2）
- aigroup Vector Memory（Wave 6.1）

**未迁移**（aigroup 保留原仓库）：

- LangGraph 运行时（kivi-agent 用自研 `AgentLoop`，不引入）
- 企业治理 E01~E25（SSO / RBAC / 模型网关 / HA）— 个人版范围外
- 真实生产 RAG/DB（保留 Adapter + Mock + 配置 + 健康检查 + 切换机制）
- 前端 Tool Bridge 完整版（demo 4 做了基础地图 Tool，完整 Bridge 未做）
- Redis Streams Exporter
- Cross-Encoder Reranker

### 6.4 Wave 7 → Wave 8 候选

按 `docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md` §七：

- **Wave 8.1**：生产部署（k8s manifest / Helm / TLS / 多副本）
- **Wave 8.2**：真实 LLM 端到端（无 ANTHROPIC_API_KEY 限制的完整 E2E）
- **Wave 8.3**：多租户隔离（authn / authz / quota）
- **Wave 8.4**：Cross-Encoder Reranker 升级 + Redis Streams Exporter

是否进入 Wave 8 取决于"对内演示 / 对外开源 / 公司生产"的最终方向（之前问过用户，**尚未收到答复**）。

---

## 附录：常见问题（FAQ）

**Q：必须用 Docker 吗？**
A：不一定。`minimal` 模式完全不需要 Docker；`web` 模式也不需要；只有 `full` 模式（Vector Memory）需要 Elasticsearch。

**Q：必须用真实 API Key 吗？**
A：`full` 模式如果不接 OpenAI Embedding，可以用 `KIVI_EMBEDDING_PROVIDER=fake`（SHA-512 伪随机）。但 LLM 主体仍需 `ANTHROPIC_API_KEY`（除非用 Mock Provider 跑测试）。

**Q：能离线跑吗？**
A：可以。所有 Python 依赖可离线 `uv pip install`；TUI + Gateway + 业务 Tool Mock 模式都不联网；只有 LLM 调用 + 真实 Embedding + ES 同步需要联网。

**Q：怎么加新的业务 Tool？**
A：参考 [docs/development/modules.md §business](docs/development/modules.md) + [docs/development/contributing.md](docs/development/contributing.md)。

**Q：怎么加新的 Profile？**
A：在 `src/kivi_agent/core/agents/builtin/business/` 加 TOML，参考 `general.toml` / `rag.toml` 格式。

**Q：怎么调试？**
A：设 `KAMA_LOG_LEVEL=DEBUG`，看 `~/.kivi/logs/core.log`。前端调试用 Chrome DevTools（WebSocket 面板可看实时事件流）。

**Q：测试在哪？**
A：`tests/unit/` 单元、`tests/integration/` 集成、`tests/e2e/` E2E、`tests/contract/` 契约测试、`tests/fixtures/` 共享 fixture。

**Q：跑 5 演示的命令？**
A：`uv run python -m demos.run_all`（WT-K2 交付后）；当前 wave 内为各 demo 单独跑。
