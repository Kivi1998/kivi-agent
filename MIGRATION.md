# 迁移清单

> **kivi-agent = KamaClaude 底座 + aigroup 业务能力 + mewcode 44 项能力 + Wave 6.1 Vector Memory + Wave 7 演示收口**。
> 本文档是**已迁移 / 未迁移 / 后续计划**的官方清单。
> 详细迁移记录（commit 列表、测试数据、已知调整）见 [docs/迁移记录/最小闭环验收记录.md](docs/迁移记录/最小闭环验收记录.md)。

## 目录

- [1. 已迁移](#1-已迁移)
- [2. 未迁移](#2-未迁移)
- [3. 后续计划（Wave 8 候选）](#3-后续计划wave-8-候选)
- [4. 迁移里程碑](#4-迁移里程碑)
- [5. 来源仓库](#5-来源仓库)

---

## 1. 已迁移

按 Wave 列：Wave 1（mewcode 8 子包）/ Wave 2（5 Profile + BusinessRouter）/ Wave 3（Web Chat）/ Wave 4（RAG + DB Adapter）/ Wave 5.1（Eval 基础 + Trace Dashboard）/ Wave 5.2（T11 + T12）/ Wave 6.1（Vector Memory）/ Wave 7（演示收口）。

### 1.1 Wave 1：mewcode 能力合并第 1 阶段（2026-07-22）

**总净 commit**：35（5 子包 + 2 集成 fix + 2 ruff）

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| mewcode | A Core | `RunContext v1` / `AgentProfile 5 字段` / `MemoryBackend Protocol + LocalMemoryBackend` / 6 事件 / `SessionCancel` 命令组 | `core/runner/run_context.py`, `core/agents/profile.py`, `core/bus/events.py`, `core/bus/commands.py` |
| mewcode | B Skills | `SkillDefinition` 双模式 / `SkillRegistry` 内存索引 / `SkillContentReader` 渐进式披露 / `ScriptExecutor` 受控执行 / 6 内建 Skill / `SkillManager` 整合 | `core/skills/` 整包 |
| aigroup | C 业务 Tool | `BaseBusinessTool` + 6 业务 Tool Mock（`web_search` / `rag_query` / `query_database` / `echarts_render` / `memory_save` / `memory_recall`） / 注册到 runner + 权限策略 | `core/business/` 整包 |
| aigroup | D Gateway | `AgentRuntime` Protocol / `RuntimeAdapter` SocketClient 桥接 / `WebSocketBridge` per-client queue / FastAPI 6 路由 + SessionCancel 集成测试 | `gateway/adapter.py`, `gateway/main.py`, `gateway/routes/` |
| aigroup | E Eval | `tests/contract/` 脚手架 + 协议期望 fixture + `EvalEmitter` + `Judge` 修复版（必填 `expected_answer` + `reference_context`） + `schema_version` 守门单测 | `tests/contract/`, `eval/judge.py` |

**集成验证**：786 passed / 0 skipped / 0 failed / 13 契约测试 0 skipped / mypy 0 / 166 source files

**契约冻结**：v1 协议冻结于 [docs/contracts/v1.md](docs/contracts/v1.md)——6 业务 Tool 名 / `RunContext` 8 字段 / `AgentProfile` 5 扩展字段 / `input_schema` 命名 / 6 类业务事件 / `SessionCancel` 命令组。

### 1.2 Wave 2：业务 Agent 真实链路（2026-07-22）

**总净 commit**：17

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | WT-A Profile | 5 业务 Profile TOML（`general` / `rag` / `web_search` / `database` / `synthesizer`） + 91 测试 + `loader.py` 最小改 | `core/agents/builtin/business/{general,rag,web_search,database,synthesizer}.toml` |
| aigroup | WT-B Router | `BusinessRouter` 关键词路由 + `RouteDecision` 数据类 + `SynthesizerRunner` 并行 + `SubResult` / `SynthesizedResult` + 24 测试 | `core/agents/business_router.py`, `core/agents/synthesizer.py` |
| aigroup | WT-C Events | `BusinessEventHandler` 订阅 6 类业务事件 + 单元 + 4 E2E + TUI 演示计划 | `core/bus/handlers/business.py`, `tests/e2e/` |

**集成验证**：918 passed / 0 failed / mypy 0 / 170 source files

**架构升级**：从"组件齐全"升级为"业务 Agent 真正能跑"——`Root Agent → BusinessRouter → 5 Profile → 6 业务 Tool → Synthesizer 汇总` 完整链路打通。

**Wave 2 收尾（TUI 接入，2026-07-23 凌晨）**：

- 5 个 widget 挂载到 TUI：`RoutePanel` / `BusinessEventWidget` / `CitationWidget` / `ChartMetadataWidget` / `SynthesizerView`（TODO）
- 业务事件轮询 `set_interval(0.3)`
- 总净 commit：10
- 集成验证：931 passed / 0 failed / mypy 0 / 175 source files

### 1.3 Wave 3：Web Chat（Vue 3 + FastAPI Gateway 真实联调）（2026-07-23 凌晨）

**总净 commit**：27

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | WT-E1 Gateway | event_bridge（订阅 6 类业务事件）+ heartbeat（15s ping）+ replay（100 条缓存 + since 重传）+ main.py 集成 + 错误码标准化双轨 | `gateway/event_bridge.py`, `gateway/heartbeat.py`, `gateway/replay.py` |
| aigroup | WT-E2 Vue | Vite + Vue 3 + TS + Pinia + vue-router + 4 基础组件 + 14 测试 | `apps/web-chat/src/main.ts`, `App.vue`, `router.ts` |
| aigroup | WT-E3 Components | useBusinessEvents composable + RoutePanel + CitationWidget + ChartWidget（ECharts 真画图）+ 20 测试 | `apps/web-chat/src/composables/useBusinessEvents.ts`, `components/RoutePanel.vue`, `components/ChartWidget.vue` |
| aigroup | WT-E4 WS State | useWebSocket 5 状态机 + 指数退避重连 + useCancel + useErrorHandler + 3 UI 组件 + 21 测试 | `apps/web-chat/src/composables/useWebSocket.ts`, `useCancel.ts`, `useErrorHandler.ts` |
| aigroup | WT-E5 E2E | Playwright + FakeAgentRuntime 470 行 mock + 4 场景 + 4 截图（1280×720+） | `tests/e2e_webchat/`, `tests/fixtures/` |

**集成验证**：后端 952 passed / 0 failed / mypy 0 / 178 source files；前端 55 passed / 0 failed / type-check 0 / lint 0 / build success

**产品形态**：Web Chat 端到端打通——浏览器创建会话 / 发送任务 / 看流式响应 / 看路由决策 + RAG 引用 + ECharts 真画图 / 取消 / 重连 / 错误恢复。

### 1.4 Wave 4：真实 rag-kb 接入 + 数据库 Adapter（2026-07-23 凌晨）

**总净 commit**：20

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | WT-F1 RAG | `RagSource`/`RagSearchResult` 数据类型 + `RagKbClient` HTTP 客户端（httpx + 健康检查 + 测试 seam）+ `RagQueryTool` 接 `RagKbClient` + 失败降级 | `core/rag/types.py`, `core/rag/client.py`, `core/business/rag_query.py` |
| aigroup | WT-F2 DB | `DatabaseAdapter` Protocol + `MockAdapter`（内存表）+ `SQLiteAdapter`（aiosqlite）+ `PostgresAdapter`（asyncpg）+ `QueryDatabaseTool` 接 Adapter + 失败降级 | `core/db/{__init__,mock,sqlite,postgres}.py`, `core/business/query_database.py` |
| aigroup | WT-F3 Config | `ConfigRuntime`（环境变量 > TOML > 默认值加载）+ `RuntimeConfig` dataclass + `/health/detailed` 端点（207 Multi-Status）+ `config.example.toml` | `core/config_runtime.py`, `gateway/health.py`, `config.example.toml` |
| aigroup | WT-F4 E2E | `InProcessRagKbServer`（FastAPI in-process）+ `docker-compose.test.yml`（Postgres 16-alpine）+ `tests/sql/init.sql` + 11 E2E 场景（4 RAG 真实 + 4 DB 真实 + 3 健康检查降级）+ conftest.py（NO_PROXY 旁路） | `tests/e2e_real/`, `tests/sql/init.sql`, `docker-compose.test.yml` |

**集成验证**：后端 999 passed / 1 skipped / 7 errors（pre-existing daemon 失败无关）/ mypy 0 / 187 source files

**架构升级**：从"Mock 实现"升级为"可配置 Adapter + 真实服务调用"——RAG HTTP + DB Adapter + 配置系统 + 健康检查 + 切换机制全部就绪。本地 rag-kb 起得来走真实，起不来自动降级到 Mock；数据库可走 SQLite / Mock，Postgres 仅在 Docker 测试场景使用。

### 1.5 Wave 5.1：Eval 基础 + Trace Dashboard（2026-07-23 上午）

**总净 commit**：21

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | G1 Eval | `EvalDataset` / `EvalResult` / `EvalRunner` / `kivi-eval` CLI | `eval/{dataset,result,runner,judge,runner_executor}.py`, `cli/eval.py` |
| aigroup | G2 Metrics | 7 指标 + `MetricsReport`（`task_success_rate` / `route_accuracy` / `tool_selection_accuracy` / `rag_citation_accuracy` / `avg_latency_seconds` / `total_tokens` / `total_cost_usd`） | `eval/metrics/{base,task_success,route_accuracy,tool_accuracy,rag_citation,latency,token,cost,report}.py` |
| aigroup | G3 Store | `EvalResultStore` + Dashboard 5 端点（runs / metrics / cases / events / summary） | `eval/store.py`, `gateway/dashboard.py` |
| aigroup | G4 Dashboard | 前端 Dashboard 5 widget + 3 view + 3 路由 | `apps/web-chat/src/api/dashboard.ts`, `components/SummaryCard|RunsList|MetricsBar|TraceTimeline|CaseTable.vue`, `views/Dashboard*.vue` |

**集成验证**：后端 1070 passed / 4 skipped / 7 errors / mypy 0 / 206 source files；前端 84 passed / 0 failed / type-check 0 / lint 0 / build success

**端到端打通**：`kivi-eval run --dataset docs/eval-demos/basic-routing-10cases.jsonl` → 10/10 judged → `EvalResultStore` 注入 → `GET /api/dashboard/runs` 返回 10 个 run → `GET /api/dashboard/metrics/{run_id}` 返回 7 指标。

### 1.6 Wave 5.2：T11 多 Agent 协作 + T12 coding Agent 指标（2026-07-23 上午）

**总净 commit**：24

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | H1 Team | T11 6 指标（`team_success_rate` / `delegation_accuracy` / `handoff_quality` / `coordination_latency_s` / `agent_utilization` / `role_consistency`） | `eval/team/`, `eval/metrics/team.py` |
| aigroup | H2 Coding | 最小 coding agent（kivi 自建）+ T12 8 指标（`task_completion_rate` / `tests_passed_rate` / `patch_quality` / `iteration_count` / `time_to_first_pass_s` / `self_recovery_rate` / `compile_success_rate` / `test_growth_rate`） | `eval/coding/`, `eval/metrics/coding.py` |
| aigroup | H3 Dashboard | 5 team 端点 + 5 coding 端点 | `eval/{team,coding}_store.py`, `gateway/{team,coding}_dashboard.py` |
| aigroup | H4 前端 | 2 新视图（Team / Coding）+ 6 路由 + 10 widget | `apps/web-chat/src/{api,components,views}/` (team + coding) |

**集成验证**：后端 1224 passed / 4 skipped / 0 failed / 7 errors / mypy 0 / 221 source files；前端 143 passed / 0 failed / type-check 0 / lint 0 / build success

**端到端打通**：

- T11：5 team case 跑通，6 指标计算正确
- T12：6 coding case 在 tmpdir 沙箱跑通，8 指标计算正确

### 1.7 Wave 6.1：阶段 6 长期记忆 + 向量检索（2026-07-23 下午）

**总净 commit**：18

| 来源 | 包 | 范围 | 关键文件 |
|---|---|---|---|
| aigroup | J1 Vector Backend | `VectorMemoryBackend`（ES）+ Embedding + BM25Reranker | `core/memory/{embedding/,vector_backend,rerank}.py` |
| aigroup | J2 记忆增强 | 6 项增强：filter / dedup / audit / expire / fallback / lifecycle | `core/memory/{types,filter,dedup,audit,expire,fallback,lifecycle}.py` |
| aigroup | J3 Memory API | Gateway 记忆 API（8 端点 + MemoryItemStore） | `gateway/memory_dashboard.py`, `core/memory/store.py` |
| aigroup | J4 Memory UI | 前端记忆管理 UI（5 widget + 1 view + 1 路由） | `apps/web-chat/src/{api/memory.ts, components/memory/, views/MemoryDashboard.vue}` |

**集成验证**：后端 1387 passed / 7 skipped / 0 failed / 7 errors / mypy 0 / 235 source files；前端 178 passed / 0 failed / type-check 0 / lint 0 / build success

**阶段 6 验收对照**（整合方案 4 项）：

- ✅ 小型本地模式不依赖外部数据库也能运行（`memory_backend=local` 默认）
- ✅ 启用向量模式后只注入相关记忆（`search(query, top_k=5)`）
- ✅ 用户能查看/编辑/归档/删除记忆（8 端点 + 前端 MemoryDashboard）
- ✅ 记忆提取失败不影响主任务（`MemoryExtractionFallback.safe_extract` 永不 raise）

### 1.8 Wave 7：阶段 8 端到端整合、演示与收口（2026-07-23，本波次）

**计划**：[docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md](docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md)

| WT | 范围 | 状态 | 关键文件 |
|---|---|---|---|
| K1 | Docker Compose 三模式 + 启动脚本 + 凭据清理 | 进行中 | `docker-compose.yml`, `scripts/start.sh`, `scripts/health_check.sh`, `scripts/stop.sh`, `scripts/run_demos.sh`, `.env.example` |
| K2 | 5 演示用例脚本化（含 MapLoadTool + MapView.vue） | 进行中 | `demos/demo{1,2,3,4,5}_*.py`, `demos/fixtures/`, `demos/base.py`, `core/tools/builtin/map_load.py`, `core/agents/builtin/business/frontend_tool.toml`, `apps/web-chat/src/components/MapView.vue` |
| K3 | 故障注入 + 性能基线 + 安全基线 | 进行中 | `tests/integration/test_failure_injection.py`, `tests/performance/test_benchmarks.py`, `tests/security/test_security_baseline.py` |
| K4 | README + 架构图 + 开发指南 + 演示手册 + 迁移清单 | **本 PR 完成** | `README.md`（重写 247 行）, `RUNBOOK.md`（重写 870 行）, `docs/architecture/architecture.md`（539 行）, `docs/architecture/data-flow.md`（505 行）, `docs/development/contributing.md`（705 行）, `docs/development/modules.md`（540 行）, `docs/demo/demo{1-5}_*.md`（1677 行）, `MIGRATION.md`（本文件 200+ 行） |

**目标**：

- 新环境按 README 能启动
- 5 演示用例全过
- CLI / TUI 原能力不回退
- Web / 业务 Tool / 多 Agent / 记忆 / 评估形成完整闭环

---

## 2. 未迁移

aigroup 仓库中**部分能力未合并到 kivi-agent**——按重要性分两类。

### 2.1 完整业务 Tool 白名单（aigroup 200+ Tool vs kivi-agent 6 Tool）

**aigroup 实际有 200+ Tool**（含企业级 / 行业级 / 实验性），kivi-agent 只集成 6 个**演示版**核心 Tool。

| 类别 | aigroup 数量 | kivi-agent 已集成 | 备注 |
|---|---|---|---|
| 演示版核心 | 6 | 6（`web_search` / `rag_query` / `query_database` / `echarts_render` / `memory_save` / `memory_recall`） | v1 §1 冻结 |
| 企业业务 | ~50 | 0 | CRM / ERP / OA / HR / 财务 等 |
| 行业业务 | ~80 | 0 | 医疗 / 法律 / 教育 / 金融 等 |
| 实验性 | ~70 | 0 | A/B 测试 / 多模态 / 视频理解 等 |

**说明**：

- v1 协议冻结 6 业务 Tool 名——新增 Tool **不破坏** v1 契约（`AgentProfile.allowed_tools` 是字符串列表，可自由扩展）
- 真实生产 Tool 接入按需扩展，每次新增走"Adapter 协议 + 真实实现 + Mock fallback"三件套
- 详见 [docs/development/contributing.md](docs/development/contributing.md) "新增业务 Tool"章节

### 2.2 Frontend Tool Bridge 完整版（demo 4 只做了基础地图 Tool）

**aigroup 完整 Frontend Tool Bridge**：

- 完整 Tool 注册表（~30 Tool：地图 / 图表 / 表单 / 弹窗 / 文件上传 / 视频播放 等）
- WebSocket 双向协议（Tool 请求 + 前端响应）
- 前端 SDK（Vue / React 通用）
- 错误恢复 + 重连 + 超时

**kivi-agent 当前**：

- `MapLoadTool` 1 个 Tool（demo 4 用）
- `frontend_tool` 1 个业务 Profile
- `MapView.vue` 1 个组件
- v1 §5.2.1 冻结 2 个事件（`FrontendToolCallRequested` / `FrontendToolCallResponded`）

**说明**：

- demo 4 做了"最小可用版本"——找 GeoJSON + 加载 + WebSocket 推事件
- 完整 Bridge 留 Wave 8+ 视情况扩展
- v1 契约已留口子（2 个事件），新增 Frontend Tool 不破坏契约

### 2.3 Redis Streams Exporter

**aigroup 有**：`diit-agent-server` 把 Agent 事件通过 Redis Streams 导出，用于：

- 跨服务事件分发（多副本 Gateway）
- 事件持久化（Redis AOF / RDB）
- 第三方系统订阅（Eval / Dashboard / 监控）

**kivi-agent 当前**：

- 事件直接走 WebSocket / TUI 轮询，**不经过** Redis
- `EvalResultStore` 是进程内单例 + `.jsonl` 落盘
- 多副本 Gateway 暂未支持

**说明**：

- 单机演示版不需要 Redis Streams
- 多副本生产部署时再接入（Wave 8.1 候选）

### 2.4 Cross-Encoder Reranker

**aigroup 有**：用 Cross-Encoder 模型（BERT-based）对 RAG 召回结果精排，显著提升准确率。

**kivi-agent 当前**：

- `BM25Reranker`（轻量级关键词匹配 + 向量相似度混合）
- 没用 Cross-Encoder（需要额外模型 + 推理资源）

**说明**：

- BM25 已覆盖演示场景
- Cross-Encoder 升级留 Wave 8.4 候选

### 2.5 LangGraph / LangChain Runtime

**aigroup 用了**：原本基于 LangGraph `StateGraph` + LangChain `AgentExecutor`。

**kivi-agent 明确不做**：

- 自研 `AgentLoop`（`core/loop.py`）+ 工具注册表 + 权限 + 沙箱 + Subagent/Team
- 不引入 LangGraph / LangChain 作为运行时框架
- 详见整合方案 §3 明确不做的事

**原因**：

- 整合方案核心原则：保留 kivi-agent 自研 Agent Runtime
- LangGraph 与自研 Runtime 是两个不同范式，强行混用会增加复杂度
- aigroup 的 LangGraph 代码已在 Wave 1 全部重写为 kivi 原生

### 2.6 企业治理（E01~E25，25 项）

**aigroup 有 25 项企业治理能力**（SSO / RBAC / 模型网关 / HA / 网页工作台 / 计费 / 多租户 等）。

**kivi-agent 明确不做**：

- 整合方案明确："不要求在第一阶段建设完整企业级 RBAC、SSO、计费和多租户平台"
- 个人版范围外，硬塞没意义（"个人版"产品定位）
- 详见 [docs/迁移记录/最小闭环验收记录.md §未通过项与后续修复计划](docs/迁移记录/最小闭环验收记录.md)

**未来候选**：

- Wave 8.3 多租户隔离（authn / authz / quota）
- 但取决于"对内演示 / 对外开源 / 公司生产"的最终方向（用户尚未答复）

### 2.7 真实生产 rag-kb / 数据库服务

**用户决定（2026-07-23）**：

- kivi-agent 通过 HTTP API 调用 rag-kb，**不迁移 / 不重写 rag-kb**
- 数据库：可配置 Adapter + Mock 保底，**不接生产数据库**
- 不用真实云服务 / Key

**kivi-agent 当前**：

- `RagKbClient` + `DatabaseAdapter` 全部就位
- 本地 rag-kb 起得来走真实，起不来自动降级到 Mock
- 数据库可走 SQLite / Mock，Postgres 仅在 Docker 测试场景使用
- 真实生产服务**保留 Adapter + Mock + 配置 + 健康检查 + 切换机制**

---

## 3. 后续计划（Wave 8 候选）

按整合方案 §10 阶段 8 之后路线 + Wave 7 计划 §七 + 当前现状，Wave 8 候选如下。

> **是否进入 Wave 8 取决于"对内演示 / 对外开源 / 公司生产"的最终方向**（用户尚未答复）。

### 3.1 Wave 8.1：生产部署

**目标**：从"学习探索版"升级为"生产可部署"。

**内容**：

- Kubernetes manifest（Deployment / Service / Ingress）
- Helm chart（参数化配置）
- TLS 证书（Let's Encrypt / cert-manager）
- 多副本 Gateway（Session 共享 / 事件分发）
- 健康检查 + 优雅停机
- 监控（Prometheus / Grafana）
- 日志聚合（ELK / Loki）

**前提**：

- 需要 Docker Hub 镜像仓库
- 需要 K8s 集群（或云服务）
- 需要域名 + 证书

**估时**：2-3 周

### 3.2 Wave 8.2：真实 LLM 端到端

**目标**：用真实 LLM（Anthropic / OpenAI / DeepSeek）跑完 5 demo 端到端，生成真实数据。

**内容**：

- 不依赖 `FakeLlmProvider` 的 E2E 测试
- 真实 LLM 跑 5 demo + 生成报告
- 真实 LLM 跑 Eval 数据集（10 条 routing + 6 条 coding + 5 条 team）
- 真实 LLM 跑失败注入 / 性能基线

**前提**：

- 需要真实 LLM API Key（Anthropic / OpenAI 等）
- 需要 LLM 服务稳定

**估时**：1 周

### 3.3 Wave 8.3：多租户隔离

**目标**：从"个人版"升级为"多租户 SaaS"。

**内容**：

- 身份认证（SSO / OAuth / API Key）
- 权限模型（RBAC / ABAC）
- 资源配额（token / 步数 / 存储）
- 数据隔离（per-tenant namespace）
- 计费（token 用量 → 账单）

**前提**：

- 需要后端数据库（Postgres + RLS）
- 需要 OAuth Provider
- 需要支付集成

**估时**：4-6 周

### 3.4 Wave 8.4：Cross-Encoder + Redis Streams

**目标**：补齐 aigroup 未迁移的 2 个核心能力。

**内容**：

- Cross-Encoder Reranker（BERT-based 精排）
- Redis Streams Exporter（事件分发 + 持久化）
- 升级 BM25Reranker → Cross-EncoderReranker
- 多副本 Gateway 接入 Redis Streams

**前提**：

- 需要 Cross-Encoder 模型（如 `cross-encoder/ms-marco-MiniLM-L-6-v2`）
- 需要 Redis 服务

**估时**：1-2 周

### 3.5 其他候选（按需）

- **Wave 8.5**：完整 Frontend Tool Bridge（30+ Tool + Vue / React 通用 SDK）
- **Wave 8.6**：更多业务 Tool（CRM / ERP / OA 等 50+ Tool）
- **Wave 8.7**：多模态（图片 / 视频 / 音频理解）
- **Wave 8.8**：行业 Agent（医疗 / 法律 / 教育 / 金融 等 80+ Agent）

---

## 4. 迁移里程碑

| Wave | 日期 | 范围 | 净 commit | 测试数 | mypy files | ruff errors |
|---|---|---|---|---|---|---|
| 基线 S7 (`stage/s7`) | 2026-07-20 | KamaClaude 底座 | — | 256 | 111 | 45 |
| Wave 1 | 2026-07-21~22 | mewcode 8 子包 | 35 | 404 | 134 | 61 |
| Wave 2 | 2026-07-22 | 5 Profile + Router | 17 | 786 | 170 | 61 |
| Wave 2 收尾 | 2026-07-23 凌晨 | TUI 接入 | 10 | 931 | 175 | **45**（-16） |
| Wave 3 | 2026-07-23 凌晨 | Web Chat | 27 | 952 后端 + 55 前端 | 178 后端 | 45 |
| Wave 4 | 2026-07-23 凌晨 | RAG + DB Adapter | 20 | 999 | 187 | 45 |
| Wave 5.1 | 2026-07-23 上午 | Eval + Trace Dashboard | 21 | 1070 后端 + 84 前端 | 206 | 45 |
| Wave 5.2 | 2026-07-23 上午 | T11 + T12 | 24 | 1224 后端 + 143 前端 | 221 | 45 |
| Wave 6.1 | 2026-07-23 下午 | Vector Memory | 18 | 1387 后端 + 178 前端 | **235** | 45 |
| Wave 7 | 2026-07-23 | 演示收口 | 4-5 文档 + 演示 | 1407+ | 235+ | 45 |
| **累计** | 2026-07-23 | **整合完成** | **~190** | **1407+** | **235+** | **45** |

**说明**：

- ruff 45 errors 是**仓库基线**（pre-existing line-too-long），Wave 1 之后**新增 0**（已收口）
- 7 errors 是 pre-existing daemon subprocess 失败（需 `ANTHROPIC_API_KEY`），与 Wave 无关
- 详细每个 Wave 的集成数据见 [docs/迁移记录/最小闭环验收记录.md](docs/迁移记录/最小闭环验收记录.md)

---

## 5. 来源仓库

kivi-agent 整合自以下 3 个仓库：

| 仓库 | 路径 | 角色 | 整合方式 |
|---|---|---|---|
| **KamaClaude** | `/Users/kivi/Documents/agent系统/Kama/KamaClaude` | 底座（自研 Agent Runtime） | 改名 + 继承全部能力 |
| **aigroup/diit-llm-framework** | `/Users/kivi/Documents/agent系统/aigroup/diit-llm-framework` | 业务能力（业务 Tool / Web Chat / Eval / Vector Memory） | 协议冻结 + 重写为 kivi 原生 |
| **mewcode** | （已合入 KamaClaude / aigroup） | 44 项能力（M01~M44） | 集成到 Wave 1 各子包 |

**整合方案**：[kivi-agent与aigroup整合实施方案.md](../kivi-agent与aigroup整合实施方案.md)（位于 `/Users/kivi/Documents/agent系统/`）

**整合核心原则**：

- 保留 kivi-agent 自研 Agent Runtime，不引入 LangGraph / LangChain
- 业务运行时是否并行、并行多少 Agent，由具体任务决定（**不固定数量**）
- 先完成学习演示版，不以高可用、租户隔离、复杂权限平台为第一阶段目标
- 所有接口要保留继续产品化的空间

---

## 6. 后续阅读

- **[README.md](README.md)**：项目入口
- **[RUNBOOK.md](RUNBOOK.md)**：运维手册（配置 / 启停 / 故障排查）
- **[docs/architecture/architecture.md](docs/architecture/architecture.md)**：整体架构
- **[docs/architecture/data-flow.md](docs/architecture/data-flow.md)**：数据流
- **[docs/development/contributing.md](docs/development/contributing.md)**：贡献指南
- **[docs/development/modules.md](docs/development/modules.md)**：模块说明
- **[docs/demo/demo{1-5}_*.md](docs/demo/)**：5 演示手册
- **[docs/迁移记录/最小闭环验收记录.md](docs/迁移记录/最小闭环验收记录.md)**：每个 Wave 的详细集成记录
- **[docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md](docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md)**：Wave 7 计划书
- **[WIRE_PROTOCOL.md](WIRE_PROTOCOL.md)**：IPC 协议定义（自动生成）
- **[../kivi-agent与aigroup整合实施方案.md](../kivi-agent与aigroup整合实施方案.md)**：整合主方案
