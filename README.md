# kivi-agent

> 自研 Agent Runtime + 业务 Agent + Web Chat + 长期记忆 + Eval Dashboard 的**学习探索版**通用 Agent 平台。
> 整合 kivi 自研核心 + aigroup 业务能力，**不引入 LangGraph / LangChain 运行时**。

## 这是什么

`kivi-agent` 是一个**常驻守护进程驱动的本地 AI Agent 系统**：

- **Core Daemon**（`kivi-core`）作为常驻进程处理所有 LLM 调用、工具执行、权限审批、Subagent/Team 协作
- **CLI**（`kivi`）和 **TUI**（`kivi-tui`）通过 TCP loopback 与 Daemon 通信
- **Web Chat**（Vue 3 + FastAPI Gateway）通过 WebSocket 实时推送业务事件
- **业务能力**：编程 Agent / 知识库 RAG / 数据库问数 / 前端地图 / 综合多 Agent
- **长期记忆**：本地 Markdown（默认）+ Elasticsearch 向量检索（可选）
- **评测体系**：JSONL 数据集 + 7 维度指标 + 5 Dashboard 端点 + Vue Dashboard

经过 Wave 1~6.1 共 6 波迭代（35 + 17 + 27 + 20 + 21 + 24 + 18 = 162 commit，1387 passed / 235 source files / 178 frontend tests），形成可重复演示 + 可测试 + 可继续扩展的学习版成果。

## 核心价值

| 价值点 | 怎么做到的 |
|---|---|
| **自研 Runtime** | `AgentLoop` + 工具注册表 + 权限 + 沙箱 + Subagent/Team；不依赖 LangGraph |
| **业务 Tool 100% Mock 起步** | 6 个业务 Tool（`web_search` / `rag_query` / `query_database` / `echarts_render` / `memory_save` / `memory_recall`）可降级到 Mock，真实 Adapter 可配置切换 |
| **5 路由 Profile** | `BusinessRouter` 关键词路由 → 5 个业务 Profile（`general` / `rag` / `web_search` / `database` / `synthesizer`） |
| **3 启动模式** | `minimal`（仅 Core + CLI/TUI）/ `web`（+ Gateway + Web Chat）/ `full`（+ ES + Redis + Eval） |
| **5 演示用例** | 编程 / RAG / 数据库 / 前端地图 / 综合多 Agent，每个可重跑 + 输出报告 |
| **完整 Dashboard** | Trace + Metrics + Memory + Team + Coding 5 个 Dashboard 视图 |

## 环境要求

| 依赖 | 版本 | 用途 |
|---|---|---|
| 操作系统 | macOS / Linux | Core Daemon 用 Unix 域套接字或 TCP loopback |
| Python | 3.12.x | 由 `uv` 自动管理，无需手动安装 |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Python 依赖 + 脚本入口管理 |
| Node.js | ≥ 20.x | Web Chat 前端开发（`apps/web-chat/`） |
| Docker | ≥ 24.0（可选） | `full` 模式需要起 Elasticsearch |

安装 uv（若尚未安装）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Python 3.12 由 uv 自动管理（参见 `.python-version`）。

## 快速开始

按你的使用场景选择 3 种模式之一。所有模式都以 `uv sync` + 拷贝 `.env.example .env` 作为前置步骤。

### 前置步骤（3 模式共用）

```bash
git clone <repo> && cd kivi-agent
uv sync                                  # 安装 Python 依赖
cp .env.example .env                     # 创建本机配置（不提交）
```

### 模式 1：minimal（仅 Core + CLI/TUI，零外部依赖）

适合本地开发、跑 TUI、跑 5 演示。

```bash
uv run kivi-core &                       # 启动 Core Daemon（后台）
uv run kivi ping                         # 验证连通：应返回 pong
uv run kivi --version                    # 应输出 0.0.1
```

```bash
# 启动 TUI（Textual 终端界面）
uv run kivi-tui
```

### 模式 2：web（Core + Gateway + Web Chat）

适合 Web 演示、Playwright E2E、查看 Dashboard。

```bash
# 终端 1：启动 Core Daemon
uv run kivi-core &

# 终端 2：启动 FastAPI Gateway（默认 8000 端口）
uv run kivi-gateway                     # 端口默认 8000，前端通过 /api 反向代理

# 终端 3：启动 Vue 3 前端开发服务器（默认 5173 端口）
cd apps/web-chat && npm install && npm run dev
```

打开浏览器访问 `http://localhost:5173`，应看到 Chat 页面。

**curl 验证**：

```bash
# Core 健康
curl -fsS http://127.0.0.1:7437/health
# Gateway 健康
curl -fsS http://127.0.0.1:8000/health
# Gateway 详细健康（207 Multi-Status）
curl -fsS http://127.0.0.1:8000/health/detailed
# 前端代理到 Gateway
curl -fsS http://127.0.0.1:5173/api/dashboard/summary
```

### 模式 3：full（+ Elasticsearch + Eval Dashboard）

适合 Vector Memory 演示 + Eval 端到端。

```bash
# 终端 1：起 Elasticsearch（单节点 1GB heap，dev mode）
docker-compose up -d                     # 起 ES 到 localhost:9200

# 终端 2：Core Daemon（启用 vector memory）
KIVI_MEMORY_BACKEND=vector uv run kivi-core &

# 终端 3：Gateway
uv run kivi-gateway

# 终端 4：跑 5 演示（端到端）
uv run python -m demos.run_all
```

**curl 验证**：

```bash
# ES 集群健康
curl -fsS http://localhost:9200/_cluster/health
# Core 通过 vector backend 检索
curl -fsS 'http://127.0.0.1:8000/api/memory/search?query=hello'
```

## Quick Start：Real LLM（Wave 8.2 新增）

> **本节定位**：用户 export 真实 LLM key 后，**3 行命令**跑通 5 demo + 5 eval case 端到端。
> **核心原则**：默认**全部跳过**（env guard `KIVI_RUN_E2E=1` 才跑），**不主动扣 token**。
> **完整指南**：[docs/e2e-real/README.md](./docs/e2e-real/README.md)

### 选一种 key 接入

```bash
# 选项 1：官方 Anthropic（推荐）
export KIVI_ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx

# 选项 2：OpenAI 官方
# export KIVI_OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx
# export KIVI_OPENAI_MODEL=gpt-4o-mini

# 选项 3：DeepSeek（最便宜，约 Anthropic 1/30）
# export KIVI_ANTHROPIC_API_KEY=sk-deepseek-xxxxxxxxxxxx
# export KIVI_ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
# export KIVI_LLM_DEFAULT_MODEL=deepseek-chat
```

### 一行命令跑真 LLM

```bash
# 启用真实 LLM 测试 + 限制 case 数量（防 token 失控）
export KIVI_RUN_E2E=1
export KIVI_E2E_PROVIDER=anthropic   # 或 openai
export KIVI_E2E_MAX_CASES=5

# 跑 5 demo + 5 eval case
uv run pytest tests/e2e_real -q

# 报告输出到 reports/e2e_real/（JSON + Markdown 双格式）
ls -la reports/e2e_real/
# → real_llm_run_20260723_143021.json
# → real_llm_run_20260723_143021.md
```

### 报告样例（Markdown）

```markdown
## 汇总

| 指标 | 值 |
|---|---|
| Provider | anthropic |
| Model | claude-sonnet-4-6 |
| Total Cases | 10 |
| Success Rate | 100% (10/10) |
| Total Tokens | 12,345 |
| Total Cost (USD) | $0.0876 |
| Avg Latency | 3.42s |
```

### 简历引用

跑完后复制 [docs/e2e-real/RESULTS_TEMPLATE.md](./docs/e2e-real/RESULTS_TEMPLATE.md) → 填实际数据 → 改名为 `RESULTS.md` → 提交到仓库。

```markdown
## Real LLM End-to-End Results

> **项目**：kivi-agent
> **Wave 8.2**：用 anthropic claude-sonnet-4-6 跑通 5 demo + 5 eval case（10/10 通过）
> **端到端延迟**：3.42 秒/case
> **Token 成本**：$0.0876 / 全量 10 case
> **复现**：`KIVI_RUN_E2E=1 uv run pytest tests/e2e_real -q`
```

### 详细文档

- **[docs/e2e-real/README.md](./docs/e2e-real/README.md)**：完整指南（3 种 key 接入 + 怎么跑 + 怎么读 + 怎么控制成本 + 故障排查 + 架构）
- **[docs/e2e-real/RESULTS_TEMPLATE.md](./docs/e2e-real/RESULTS_TEMPLATE.md)**：报告模板（跑完后填，简历可引用）
- **[RUNBOOK.md §4 真实 LLM 端到端](./RUNBOOK.md#4-真实-llm-端到端wave-82-新增)**：运维视角的操作手册

---

## 5 演示用例（端到端可重跑）

| # | 演示 | 能力 | 文档 |
|---|---|---|---|
| 1 | **编程 Agent**：修 bug + 跑 pytest | 最小 coding agent + 8 指标 | [docs/demo/demo1_coding.md](docs/demo/demo1_coding.md) |
| 2 | **知识库 Agent**：问内部政策 | RAG HTTP 客户端 + 引用溯源 | [docs/demo/demo2_rag.md](docs/demo/demo2_rag.md) |
| 3 | **数据库 Agent**：自然语言问数 | DatabaseAdapter + SQL 生成 + ECharts | [docs/demo/demo3_database.md](docs/demo/demo3_database.md) |
| 4 | **前端操作 Agent**：加载 GeoJSON 地图 | `MapLoadTool` + WebSocket 推送 | [docs/demo/demo4_frontend_map.md](docs/demo/demo4_frontend_map.md) |
| 5 | **综合多 Agent**：政策 + 外部 + 图表 + 团队 | BusinessRouter + Synthesizer + 6 业务事件 | [docs/demo/demo5_multi_agent.md](docs/demo/demo5_multi_agent.md) |

```bash
# 跑单个 demo
uv run python -m demos.demo1_coding

# 跑全部 5 demo + 汇总报告
uv run python -m demos.run_all
# → reports/demo_summary.json（每个 demo pass/fail + 耗时）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| **[RUNBOOK.md](./RUNBOOK.md)** | 配置详解、启停操作、开发命令、故障排查 7 场景、监控 / 日志、升级指南 |
| **[docs/architecture/architecture.md](docs/architecture/architecture.md)** | 整体架构 + 模块说明 + 5 个核心流程 sequence 图 |
| **[docs/architecture/data-flow.md](docs/architecture/data-flow.md)** | 数据流（user input → LLM → tool → memory → response）+ 关键数据结构 |
| **[docs/development/contributing.md](docs/development/contributing.md)** | 代码风格、测试规范、PR 流程、Commit 规范、Sub-agent 任务模板 |
| **[docs/development/modules.md](docs/development/modules.md)** | 按目录分章节的模块说明（core / agents / business / skills / tools / memory / gateway / eval / tui / web-chat） |
| **[docs/demo/demo1~5_*.md](docs/demo/)** | 5 个演示手册：输入 / 期望输出 / 复现命令 / 故障排查 |
| **[MIGRATION.md](./MIGRATION.md)** | 已迁移 / 未迁移 / 后续计划清单（从 kama + aigroup 合并到 kivi-agent） |
| **[WIRE_PROTOCOL.md](./WIRE_PROTOCOL.md)** | IPC 协议定义（**由代码自动生成，请勿手动编辑**） |

## 贡献

欢迎贡献！请阅读 [docs/development/contributing.md](docs/development/contributing.md) 了解：

- 代码风格（ruff + mypy 严格 + 中文 docstring + 测试注释规范）
- 测试规范（pytest + env guard）
- PR 流程（4-WT 并行 → 主控集成）
- Commit 规范（`feat` / `fix` / `docs` / `chore` / `test`）
- Sub-agent 任务模板（4-WT 并行执行的工作流）

快速开始贡献：

```bash
# 1. 切分支
git checkout -b feat/your-feature

# 2. 写代码 + 写测试
# 3. 本地验证
uv run ruff check src tests
uv run mypy src
uv run pytest tests/unit -v

# 4. 提交
git commit -m "feat(scope): your feature"
# 5. push + 提 PR
```

## 安全声明

> **⚠️ 切勿提交真实 API Key、数据库密码或其他机密凭据到 git 仓库。**

kivi-agent 的安全设计：

- `.env` 文件在 `.gitignore` 中强制排除
- `.env.example` 模板**不含任何真值**，仅做格式说明
- LLM API Key 通过 `ANTHROPIC_API_KEY` 环境变量传入（不写代码）
- OpenAI Embedding Key 通过 `OPENAI_API_KEY` 传入
- 凭据清理：`git filter-repo` / BFG 已用于历史清理；Wave 7 集成期验证
- 路径遍历防护：所有 ID 参数（含 `run_id` / `memory_id` / `case_id`）拒绝 `..`
- 沙箱隔离：bash 工具走 Seatbelt / Bubblewrap（macOS / Linux）

如发现安全漏洞，请私下联系维护者，**不要**公开 issue。

## 验证清单（5 分钟快速过）

```bash
# 1. 安装 + 配置
uv sync && cp .env.example .env

# 2. 启 Core Daemon + 验证
uv run kivi-core &
sleep 2
uv run kivi ping
# → pong server=0.0.1 uptime=12ms latency=2ms

# 3. 跑测试
uv run pytest tests/unit -q
# → 1387 passed, 7 skipped, 0 failed, 7 errors
#    （7 errors 是 pre-existing daemon subprocess 失败，需 ANTHROPIC_API_KEY）

# 4. 类型检查
uv run mypy src
# → Success: no issues found in 235 source files

# 5. Lint
uv run ruff check src tests
# → 45 errors（pre-existing baseline；Wave 7 新增 0）

# 6. 前端验证（如启动了 web 模式）
cd apps/web-chat && npm test
# → 178 passed in 4.13s
```

## 状态与路线图

- ✅ **Wave 1~6.1** 已合入 main：自研 Core + Skills + 业务 Tool + Gateway + Web Chat + 真实 RAG/DB + Eval + 长期记忆
- ✅ **Wave 7**：阶段 8 演示收口（Docker Compose 三模式 + 5 演示 + 故障/性能/安全基线 + 文档）
- ✅ **Wave 8.2**（本波次）：真实 LLM 端到端（Anthropic + OpenAI 双 provider + E2E 框架 + 报告模板）— 详见 [§Quick Start: Real LLM](#quick-startreal-llmwave-82-新增) 和 [docs/e2e-real/README.md](./docs/e2e-real/README.md)
- 🔜 **Wave 8 后续**：生产部署 / 多租户隔离 / Cross-Encoder + Redis Streams

详见 [MIGRATION.md](./MIGRATION.md) 和 [docs/superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md](docs/superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md)。

## 许可

MIT（参见 [LICENSE](./LICENSE)）。
