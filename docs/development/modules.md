# 模块说明

> kivi-agent 按 `src/kivi_agent/` 目录组织，每个目录是一个子系统。
> 本文档是 [architecture.md](../architecture/architecture.md) 的文件视角补充——按目录分章节，每个模块 1-2 段说明 + 关键文件清单。

## 目录

- [1. `core/` 核心层](#1-core-核心层)
- [2. `core/agents/` Agent 体系](#2-coreagents-agent-体系)
- [3. `core/business/` 业务 Tool](#3-corebusiness-业务-tool)
- [4. `core/tools/` 工具注册表](#4-coretools-工具注册表)
- [5. `core/skills/` Skills 2.0](#5-coreskills-skills-20)
- [6. `core/mcp/` MCP 协议](#6-coremcp-mcp-协议)
- [7. `core/memory/` 长期记忆](#7-corememory-长期记忆)
- [8. `core/db/` 数据库 Adapter](#8-coredb-数据库-adapter)
- [9. `core/rag/` RAG](#9-coragerag-rag)
- [10. `core/llm/` LLM Provider](#10-corellm-llm-provider)
- [11. `gateway/` Web Gateway](#11-gateway-web-gateway)
- [12. `eval/` 评测](#12-eval-评测)
- [13. `tui/` 终端 UI](#13-tui-终端-ui)
- [14. `cli/` 命令行入口](#14-cli-命令行入口)
- [15. `apps/web-chat/` Web 端](#15-appsweb-chat-web-端)

---

## 1. `core/` 核心层

**职责**：Core Daemon 入口、AgentLoop 主循环、事件总线、权限、沙箱、上下文压缩、文件历史、Worktree 隔离。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/__init__.py` | 包入口 |
| `core/__main__.py` | `python -m kivi_agent.core` 入口 |
| `core/app.py` | Core Daemon 主入口（`kivi-core` 命令） |
| `core/runner.py` | `AgentRunner` 组装点（Provider + Bus + ToolRegistry + PermissionManager + SkillManager） |
| `core/loop.py` | `AgentLoop`（LLM ↔ Tool 循环主体） |
| `core/runs.py` | Run 生命周期管理 |
| `core/session/` | 会话存储 + checkpoint |
| `core/bus/` | EventBus + Event 联合 + Command schema（**WIRE_PROTOCOL.md 自动生成**） |
| `core/permissions/` | PermissionPolicy + PermissionManager |
| `core/sandbox/` | BashTool 沙箱（Seatbelt / Bubblewrap） |
| `core/hooks/` | Hook 系统（pre/post tool call） |
| `core/compact/` | 上下文压缩 + 熔断 |
| `core/filehistory/` | FileHistory 快照 + rewind_file |
| `core/workspace/` | Worktree 隔离 |
| `core/task/` | Task 跟踪 |
| `core/events/` | 业务事件聚合（Wave 2+） |
| `core/context/` | ExecutionContext 注入 |
| `core/config.py` | 主配置（KamaConfig） |
| `core/config_runtime.py` | 运行时配置（环境变量 + TOML + 默认值，Wave 4+） |
| `core/logging_setup.py` | 日志初始化 |

**关键设计**：

- `core/runner.py::_build_registry()` 是**所有 Tool 登记点**，新增 Tool 必须在这里 `register()`，并加 `# <tool_name>（agent: <name>）` 锚点注释
- `core/permissions/policy.py::DEFAULT_POLICIES` 是**所有 Tool 策略登记点**，新增 Tool 必须加 `ToolPolicy` 条目
- `core/bus/events.py` 的 `Event` 联合是 v1 §5.2.1 冻结，**不能改既有事件，只能加新事件**

---

## 2. `core/agents/` Agent 体系

**职责**：Agent Profile 模型、BusinessRouter 路由、Synthesizer 汇总、Team 协作、Subagent 派生。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/agents/__init__.py` | 包入口 |
| `core/agents/profile.py` | `AgentProfile` 模型（v1 §3 冻结 5 扩展字段） |
| `core/agents/loader.py` | Profile 加载器（TOML → `AgentProfile`） |
| `core/agents/business_router.py` | `BusinessRouter`（关键词路由 → `RouteDecision`） |
| `core/agents/synthesizer.py` | `SynthesizerRunner`（多 Profile 并行 + LLM 汇总） |
| `core/agents/builtin/` | 内建 Profile（TOML 格式） |
| `core/agents/builtin/coordinator.toml` | 协调者 Profile（只调度不编码） |
| `core/agents/builtin/business/general.toml` | 通用业务 Profile（无业务 Tool） |
| `core/agents/builtin/business/rag.toml` | RAG 业务 Profile（allowed_tools=[rag_query]） |
| `core/agents/builtin/business/web_search.toml` | 联网搜索 Profile |
| `core/agents/builtin/business/database.toml` | 数据库 Profile（含 echarts_render） |
| `core/agents/builtin/business/synthesizer.toml` | 汇总 Profile（无业务 Tool） |
| `core/agents/builtin/frontend_tool.toml` | 前端操作 Profile（**Wave 7 demo 4 新做**） |
| `core/teams/` | Team / TeammateInfo / Mailbox / TeamManager（多 Agent 团队协作） |
| `core/teams/models.py` | Team 数据模型 |
| `core/teams/mailbox.py` | 文件系统 Mailbox（O_CREAT\|O_EXCL 自旋锁） |
| `core/teams/manager.py` | TeamManager + team_create 工具 |
| `core/subagent/` | Subagent 派生（`spawn_background_subagent`） |

**关键设计**：

- Profile 用 TOML 描述，运行时通过 `loader.load_profile(name)` 加载
- `BusinessRouter.route(query)` 是**路由决策的唯一入口**，所有业务任务都从这里走
- `SynthesizerRunner.run(sub_results)` 是**多意图合并的唯一入口**，必须保留引用透传 + 不编造原则

---

## 3. `core/business/` 业务 Tool

**职责**：6 个业务 Tool 的实现（Mock + 真实 Adapter 切换），通过 `BusinessRouter` 被业务 Profile 调度。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/business/__init__.py` | 包入口 |
| `core/business/base.py` | `BaseBusinessTool` 抽象类（`name` / `description` / `input_schema` / `run`） |
| `core/business/web_search.py` | 网络搜索（Mock + 真实 Adapter 待接入） |
| `core/business/rag_query.py` | RAG 知识库查询（Mock + HTTP RagKbClient，Wave 4） |
| `core/business/query_database.py` | 数据库查询（Mock + SQLite/Postgres Adapter，Wave 4） |
| `core/business/echarts_render.py` | ECharts 图表渲染元数据（仅返回 option_dict，不真正画） |
| `core/business/memory_save.py` | 长期记忆保存（接入 `MemoryItemStore`） |
| `core/business/memory_recall.py` | 长期记忆检索（top_k 相关记忆） |

**关键设计**：

- 每个 Tool 必须有 `input_schema`（v1 §4 冻结，JSON Schema）
- 6 个 Tool 名字**冻结**（v1 §1）—— 不能改名，只能新增
- Mock 模式默认开启，真实 Adapter 通过配置切换（`config.example.toml` 的 `[rag]` / `[db]` 段）
- 真实服务不可用时**自动降级到 Mock**（`auto_fallback=true`）

---

## 4. `core/tools/` 工具注册表

**职责**：工具基类、注册表、并发执行、内建工具。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/tools/__init__.py` | 包入口 |
| `core/tools/base.py` | `BaseTool`（`name` / `description` / `input_schema` / `category` / `run`），v1 §4 冻结 |
| `core/tools/registry.py` | `ToolRegistry`（`deferred` / `discovered` / `search` 机制） |
| `core/tools/executor.py` | 工具并发批次执行（`category="read"` 可并发） |
| `core/tools/categories.py` | 工具分类常量（`read` / `write` / `bash` / `other`） |
| `core/tools/builtin/bash.py` | Bash 工具（沙箱） |
| `core/tools/builtin/edit_file.py` | EditFile 工具（FileStateCache staleness） |
| `core/tools/builtin/read_file.py` | ReadFile 工具 |
| `core/tools/builtin/glob.py` | Glob 工具 |
| `core/tools/builtin/grep.py` | Grep 工具 |
| `core/tools/builtin/diff.py` | Diff 工具 |
| `core/tools/builtin/worktree.py` | Worktree 工具（enter/exit） |
| `core/tools/builtin/ask_user.py` | ask_user 工具（Future 挂起应答） |
| `core/tools/rewind_file.py` | rewind_file 工具（带 snapshot_before_rewind 自动备份） |
| `core/tools/file_history.py` | FileHistory 快照（stash 风格 .bak） |
| `core/tools/tool_search.py` | tool_search 工具（deferred 工具按关键词发现） |
| `core/tools/builtin/map_load.py` | MapLoadTool（**Wave 7 demo 4 新做**，前端地图 Tool） |

**关键设计**：

- 5 个 read 类工具标 `category="read"`：bash / read_file / glob / grep / diff
- `ToolRegistry` 支持 deferred 工具（按需加载，避免全量导入）
- `executor.py` 按 `category` 分批并发（read 类并发，write 类串行）

---

## 5. `core/skills/` Skills 2.0

**职责**：Skill 定义、注册、加载、执行——支持斜杠命令（`/review`）和 Tool Skill（被 Agent 自主调用）。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/skills/__init__.py` | 包入口 |
| `core/skills/definition.py` | `SkillDefinition`（双模式：description 摘要 / content 全量） |
| `core/skills/registry.py` | `SkillRegistry` 内存索引 + 关键词搜索 |
| `core/skills/loader.py` | `SkillContentReader` 渐进式披露 |
| `core/skills/install.py` | Skill 安装（git clone + SKILL.md 校验） |
| `core/skills/executor.py` | `ScriptExecutor` 受控执行（沙箱） |
| `core/skills/manager.py` | `SkillManager` 整合 |
| `core/skills/builtin/` | 6 个内建 Skill |
| `core/skills/builtin/review.toml` | 审查 Skill |
| `core/skills/builtin/test.toml` | 跑测试 Skill |
| `core/skills/builtin/commit.toml` | 提交 Skill |
| `core/skills/builtin/docs.toml` | 文档生成 Skill |
| `core/skills/builtin/explain.toml` | 解释代码 Skill |
| `core/skills/builtin/format.toml` | 格式化 Skill |

**关键设计**：

- `SkillDefinition` 双模式：description（始终注入） + content（调用时按需加载）
- 安装流程：git clone → 校验 SKILL.md → 写入 `~/.kivi/skills/`
- 执行流程：沙箱跑 `scripts/*.sh`，超时 30s，stdout 收集为 ToolResult

---

## 6. `core/mcp/` MCP 协议

**职责**：MCP（Model Context Protocol）客户端实现，支持 stdio / TCP / streamable_http 三种传输。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/mcp/__init__.py` | 包入口 |
| `core/mcp/client.py` | MCP 客户端（stdio / TCP / streamable_http） |
| `core/mcp/secrets.py` | `${SECRET:NAME}` 引用语法（避免明文密钥） |

**关键设计**：

- stdio：启动子进程，通过 stdin/stdout JSON-RPC
- TCP：连接远程 MCP server（host:port）
- streamable_http：HTTP POST + SSE
- 密钥引用：`${SECRET:ANTHROPIC_API_KEY}` 在 `cfg.env` 中展开，零明文

---

## 7. `core/memory/` 长期记忆

**职责**：长期记忆后端（Local Markdown / Vector Elasticsearch），含 Embedding / Rerank / 过滤 / 去重 / 审计 / 过期 / Fallback / 生命周期。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/memory/__init__.py` | 包入口 |
| `core/memory/types.py` | `MemoryType` / `MemoryStatus` / `MemoryImportance` 字面量 |
| `core/memory/backend.py` | `MemoryBackend` Protocol |
| `core/memory/local_backend.py` | `LocalMemoryBackend`（Markdown 文件，默认） |
| `core/memory/vector_backend.py` | `VectorMemoryBackend`（ES knn_vector，可选） |
| `core/memory/embedding/` | Embedding 实现 |
| `core/memory/embedding/__init__.py` | 工厂 |
| `core/memory/embedding/fake.py` | `FakeEmbedding`（SHA-512 伪随机，演示用） |
| `core/memory/embedding/openai_compat.py` | `OpenAICompatEmbedding`（OpenAI 兼容 /v1/embeddings） |
| `core/memory/rerank.py` | `BM25Reranker`（纯函数 + class 两种入口） |
| `core/memory/filter.py` | `SensitiveInfoFilter`（7 类正则） |
| `core/memory/dedup.py` | `SemanticDeduplicator`（语义去重） |
| `core/memory/audit.py` | `MemoryAuditLogger`（JSONL + 路径遍历防护） |
| `core/memory/expire.py` | `MemoryExpirer`（过期自动 archive） |
| `core/memory/fallback.py` | `MemoryExtractionFallback`（永不 raise） |
| `core/memory/lifecycle.py` | 生命周期编排（filter → dedup → write → audit） |
| `core/memory/store.py` | `MemoryItemStore`（统一 Local/Vector 入口） |
| `core/memory/extractor.py` | LLM 抽取记忆（`extract` 走 fallback 包装） |
| `core/memory/recall.py` | 检索注入（`recall_and_inject` 注入到 system prompt） |
| `core/memory/loader.py` | 加载 / 初始化 |

**关键设计**：

- `MemoryBackend` Protocol 是 Local/Vector 抽象，所有读写通过这个接口
- 5 方法都包 try/except fallback 到 Local（`save` / `get` / `search` / `list` / `delete`）
- audit 失败**不重试、不抛**（主流程优先）
- `MemoryExtractionFallback.safe_extract` 永不 raise（保证主任务不挂）
- `MemoryLifecycle` 编排：filter → dedup → write → audit（顺序固定）

---

## 8. `core/db/` 数据库 Adapter

**职责**：数据库 Adapter Protocol + Mock / SQLite / Postgres 三种实现。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/db/__init__.py` | `DatabaseAdapter` Protocol + 工厂 |
| `core/db/mock.py` | `MockAdapter`（内存表，演示用） |
| `core/db/sqlite.py` | `SQLiteAdapter`（aiosqlite） |
| `core/db/postgres.py` | `PostgresAdapter`（asyncpg） |

**关键设计**：

- 通过 `DatabaseAdapter` Protocol 抽象，调用方零侵入切换
- 路径遍历防护：SQLite 路径 `..` 拒绝 + `expanduser().resolve()` 绝对化
- `:memory:` 特殊值支持（单测用）
- `isinstance(self._adapter, (SQLiteAdapter, PostgresAdapter))` 明确区分真实 vs mock

---

## 9. `core/rag/` RAG

**职责**：RAG HTTP 客户端 + 数据类型 + 健康检查 + 失败降级。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/rag/__init__.py` | 包入口 |
| `core/rag/types.py` | `RagSource` / `RagSearchResult` 数据类型 |
| `core/rag/client.py` | `RagKbClient`（httpx + 健康检查 + 测试 seam） |

**关键设计**：

- `RagKbClient.__init__` 加 `_transport: httpx.AsyncBaseTransport | None = None` 测试 seam（生产不传）
- `RagSource.url` 加 Pydantic 验证（http:// https:// 开头，禁止 file://）—— 路径遍历最小防御
- 真实模式复用 mock 的 `_format_citation` 引用格式化（设计与数据来源解耦）
- 失败降级：rag-kb 不可用时 `rag_query` 走 Mock 模式

---

## 10. `core/llm/` LLM Provider

**职责**：LLM Provider 抽象（Anthropic / OpenAI 兼容）+ 模型目录 + 流式聚合。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `core/llm/__init__.py` | 包入口 |
| `core/llm/factory.py` | Provider 工厂（按 `llm.provider` 字段路由） |
| `core/llm/anthropic.py` | Anthropic Provider（claude-sonnet-4-6 等） |
| `core/llm/openai_compat.py` | OpenAI 兼容 Provider（DeepSeek / Moonshot / OpenAI） |
| `core/llm/catalog.py` | 模型上下文窗口统一目录（合并两个 Provider 硬编码表） |
| `core/llm/streaming_collector.py` | `StreamAccumulator` 统一流式增量聚合 |

**关键设计**：

- 不需要改任何代码即可切换 Anthropic 兼容端点（`ANTHROPIC_BASE_URL` 透明替换）
- `StreamAccumulator` 是流式聚合的唯一入口（Anthropic / OpenAI 两边都用）
- 模型上下文窗口统一在 `catalog.py`（默认回退 128_000）

---

## 11. `gateway/` Web Gateway

**职责**：FastAPI Gateway + WebSocket Bridge + Eval / Team / Coding / Memory Dashboard API。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `gateway/__init__.py` | 包入口 |
| `gateway/main.py` | FastAPI app + lifespan + WebSocket 路由 + 6 路由 |
| `gateway/adapter.py` | `RuntimeAdapter` SocketClient 桥接（`run_id → session_id` 映射） |
| `gateway/event_bridge.py` | 订阅 6 类业务事件 → WebSocket 推送 |
| `gateway/heartbeat.py` | 15s 心跳 |
| `gateway/replay.py` | 100 条事件缓存 + `since` 重传 |
| `gateway/health.py` | 健康检查（Protocol duck typing） |
| `gateway/dashboard.py` | Eval Dashboard API（5 端点：runs / metrics / cases / events） |
| `gateway/team_dashboard.py` | Team Dashboard API（5 端点） |
| `gateway/coding_dashboard.py` | Coding Dashboard API（5 端点） |
| `gateway/memory_dashboard.py` | Memory Dashboard API（8 端点：list / get / search / audit） |
| `gateway/deps.py` | 依赖注入 |
| `gateway/routes/` | 路由子包（如有） |

**关键设计**：

- `RuntimeAdapter` 维护 `run_id → session_id` 映射表（WebSocket 路由必需）
- 6 路由：sessions / runs / cancel / ws / dashboard / memory（实际是若干端点，详见各 dashboard）
- `/health/detailed` 返回 **207 Multi-Status**（部分失败仍可服务）而非 503
- 错误码标准化：保留旧 `detail` + 新 `{code, message, hint, ts}`（双轨，不破坏现有测试）

---

## 12. `eval/` 评测

**职责**：评测数据集、批量跑、7 + 6 + 8 指标、Eval / Team / Coding Store、kivi-eval CLI。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `eval/__init__.py` | 包入口 + Metrics 工厂 |
| `eval/dataset.py` | `EvalDataset` / JSONL 加载 |
| `eval/result.py` | `EvalResult` / `ToolCallRecord` / `CaseEvent` |
| `eval/runner.py` | `EvalRunner` |
| `eval/runner_executor.py` | Runner 执行器 |
| `eval/judge.py` | `Judge`（必填 `expected_answer` + `reference_context`） |
| `eval/store.py` | `EvalResultStore` 单例 |
| `eval/team_store.py` | Team 评测 Store |
| `eval/coding_store.py` | Coding 评测 Store |
| `eval/team/` | T11 多 Agent 协作 |
| `eval/team/__init__.py` | 包入口 |
| `eval/team/models.py` | `TeamCase` / `TeamDataset` / `TeamEvalResult` / `MemberOutcome` / `DelegationStep` |
| `eval/team/team_runner.py` | `TeamRunner` |
| `eval/team/team_executor.py` | 执行器 |
| `eval/team/mailbox_tracker.py` | MailboxTracker 监听 mailbox 写消费 |
| `eval/coding/` | T12 编程 Agent |
| `eval/coding/__init__.py` | 包入口 |
| `eval/coding/models.py` | Coding 评测数据 |
| `eval/coding/coding_agent.py` | 最小 `CodingAgent`（接受 spec → 改文件 → 跑 pytest） |
| `eval/coding/diff_parser.py` | unified diff 解析 |
| `eval/metrics/` | 指标 |
| `eval/metrics/__init__.py` | 指标导出 |
| `eval/metrics/base.py` | 指标基类 |
| `eval/metrics/task_success.py` | task_success_rate |
| `eval/metrics/route_accuracy.py` | route_accuracy |
| `eval/metrics/tool_accuracy.py` | tool_selection_accuracy |
| `eval/metrics/rag_citation.py` | rag_citation_accuracy |
| `eval/metrics/latency.py` | avg_latency_seconds |
| `eval/metrics/token.py` | total_tokens |
| `eval/metrics/cost.py` | total_cost_usd |
| `eval/metrics/report.py` | `MetricsReport` 汇总 |
| `eval/metrics/team.py` | T11 6 指标（team_success / delegation_accuracy / handoff_quality / coordination_latency / agent_utilization / role_consistency） |
| `eval/metrics/coding.py` | T12 8 指标（task_completion / tests_passed / patch_quality / iteration_count / time_to_first_pass / self_recovery / compile_success / test_growth） |

**关键设计**：

- 14 个指标（基础 7 + Team 6 + Coding 8，3 个重叠），全部用 `Metric[T]` 抽象
- `EvalResultStore` / `TeamStore` / `CodingStore` 都是单例可重置模式
- Team 事件**不新增** v1 §5.2.1，复用 `EvalResult.events` 字段以 `type` 字符串记录
- `test_growth_rate` 函数实现叫 `growth_rate`（避开 pytest 误收集），init 暴露 `test_growth_rate = growth_rate` 别名

---

## 13. `tui/` 终端 UI

**职责**：Textual 终端界面，含 5 widget（业务事件）+ 3 screen（会话 / 计划 / 审批）+ 团队树。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `tui/__init__.py` | 包入口 |
| `tui/__main__.py` | `kivi-tui` 入口 |
| `tui/app.py` | Textual App 主体（5 widget 挂载 + 业务事件轮询） |
| `tui/route_panel.py` | 路由决策面板（显示 BusinessRouter 决策） |
| `tui/business_event_widget.py` | 业务事件 Widget（订阅 6 类事件） |
| `tui/citation_widget.py` | RAG 引用 Widget |
| `tui/chart_metadata_widget.py` | 图表元数据 Widget |
| `tui/synthesizer_view.py` | Synthesizer 汇总视图（**TODO 挂载**） |
| `tui/permission_widgets.py` | 权限审批 Widget（拆分独立文件） |
| `tui/plan_dialog.py` | 计划模式对话框 |
| `tui/ask_user_dialog.py` | ask_user 弹窗（options + free-form 双模式） |
| `tui/session_screen.py` | 会话选择/恢复 |
| `tui/team_tree.py` | 团队树视图（订阅 `TeamCreatedEvent`） |

**关键设计**：

- 业务事件轮询：`set_interval(0.3, self._refresh_business_event_widget)`
- widget id 由 `_safe_widget_id` 正则 sanitizer（防御 `..` `/`）
- CSS `color: $text-muted` 而非 `color: dim`（Textual 8.x 不支持 dim 字面值）

---

## 14. `cli/` 命令行入口

**职责**：`kivi` / `kivi-core` / `kivi-tui` / `kivi-eval` 4 个入口命令。

**关键文件**：

| 文件 | 说明 |
|---|---|
| `cli/__init__.py` | 包入口 |
| `cli/__main__.py` | `python -m kivi_agent.cli` 入口 |
| `cli/main.py` | `kivi` 主入口（`ping` / `--version` 等） |
| `cli/eval.py` | `kivi-eval` 入口（`run` / `summary` 子命令） |
| `cli/commands/` | 命令子包（如有） |

**关键命令**：

| 命令 | 入口 | 说明 |
|---|---|---|
| `kivi` | `cli/main.py` | CLI 客户端（ping / version） |
| `kivi-core` | `core/app.py` | Core Daemon 启动 |
| `kivi-tui` | `tui/__main__.py` | Textual TUI 启动 |
| `kivi-eval` | `cli/eval.py` | 评测 CLI（run / summary） |

---

## 15. `apps/web-chat/` Web 端

**职责**：Vue 3 + Pinia + vue-router + ECharts 前端，5 Dashboard 视图（Trace / Metrics / Memory / Team / Coding）。

**关键文件**：

```
apps/web-chat/
├── package.json              # 依赖（pinia / vue-router / tailwind / echarts / vue-echarts / @vue/tsconfig）
├── vite.config.ts            # Vite + vitest 配置（含 /api + /sessions proxy 指向 gateway）
├── tsconfig.json             # 严格模式 + vitest/globals types
├── index.html                # 入口（class="dark" + bg-bg-base + icon）
├── src/
│   ├── main.ts               # 入口（Pinia + router + session API）
│   ├── App.vue               # 根组件（RouterView）
│   ├── env.d.ts              # 类型声明（含 eslint-disable 抑制）
│   ├── style.css             # 暗色主题 + CSS 变量
│   ├── router.ts             # vue-router 配置（13 路由）
│   ├── stores/               # Pinia stores（session / events）
│   ├── composables/          # useWebSocket / useBusinessEvents / useCancel / useErrorHandler
│   ├── types/                # TypeScript 类型（api.ts 等）
│   ├── api/                  # API 客户端
│   │   ├── session.ts
│   │   ├── dashboard.ts      # Eval Dashboard API
│   │   ├── team.ts           # Team Dashboard API
│   │   ├── coding.ts         # Coding Dashboard API
│   │   └── memory.ts         # Memory Dashboard API
│   ├── components/           # UI 组件
│   │   ├── MessageList.vue
│   │   ├── MessageInput.vue
│   │   ├── SessionHeader.vue
│   │   ├── SessionList.vue
│   │   ├── CancelButton.vue
│   │   ├── ConnectionStatus.vue
│   │   ├── ErrorBanner.vue
│   │   ├── RoutePanel.vue    # 路由面板
│   │   ├── CitationWidget.vue
│   │   ├── ChartWidget.vue   # ECharts 真画图
│   │   ├── SummaryCard.vue
│   │   ├── RunsList.vue
│   │   ├── MetricsBar.vue
│   │   ├── TraceTimeline.vue
│   │   ├── CaseTable.vue
│   │   ├── memory/           # Memory Dashboard 组件
│   │   ├── team/             # Team Dashboard 组件
│   │   └── coding/           # Coding Dashboard 组件
│   ├── views/                # 页面
│   │   ├── ChatView.vue              # Chat 主页面
│   │   ├── SessionList.vue           # 会话列表
│   │   ├── Dashboard.vue             # Eval Dashboard
│   │   ├── DashboardCaseDetail.vue
│   │   ├── DashboardRunDetail.vue
│   │   ├── TeamDashboard.vue         # T11 Team Dashboard
│   │   ├── TeamCaseDetail.vue
│   │   ├── TeamDashboardDetail.vue
│   │   ├── CodingDashboard.vue       # T12 Coding Dashboard
│   │   ├── CodingDashboardDetail.vue
│   │   └── MemoryDashboard.vue       # Vector Memory Dashboard
│   └── test-setup.ts         # 全局桩 ResizeObserver（vue-echarts autoresize 需要）
└── tests/                    # vitest 测试
```

**关键设计**：

- Vite proxy：开发时 `/api` + `/sessions` 反向代理到 Gateway `:8000`
- ECharts 真画图（vue-echarts `shallowMount`）
- 错误码双轨：保留旧 `detail` + 新 `{code, message, hint, ts}`（不破坏现有 13 个测试）

---

## 附录：公共登记点（不容许改）

| 文件 | 用途 | 加新条目时 |
|---|---|---|
| `core/runner.py::_build_registry()` | 工具登记 | 加 `register(...)` + `# <tool>（agent: <name>）` 注释 |
| `core/permissions/policy.py::DEFAULT_POLICIES` | 权限策略 | 加 `ToolPolicy` + 锚点注释 |
| `core/bus/events.py::Event` 联合 | 业务事件 | 加新事件类型（**不能改既有事件**） |
| `core/bus/commands.py` | Command schema | 加新命令（**不能改既有命令**） |
| `core/agents/builtin/business/` | 业务 Profile | 加新 TOML |
| `config.example.toml` | 配置示例 | 加新 section + 注释 |

**改这 6 个地方**就是改公共契约，PR 描述**必须**明确说明理由，并经主控 review。

## 后续阅读

- **[contributing.md](contributing.md)**：代码风格、测试规范、PR 流程
- **[../architecture/architecture.md](../architecture/architecture.md)**：整体架构 + 5 核心流程
- **[../architecture/data-flow.md](../architecture/data-flow.md)**：数据流 + 关键数据结构
- **[../../MIGRATION.md](../../MIGRATION.md)**：已迁移 / 未迁移 / 后续计划
