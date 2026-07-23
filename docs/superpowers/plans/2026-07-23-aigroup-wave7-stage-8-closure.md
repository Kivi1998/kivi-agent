# aigroup Wave 7：阶段 8 端到端整合、演示与收口

> **基线**：`main @ b211fc7`（aigroup Wave 6.1 收官，1395 passed / 235 files / Vector Memory）
> **日期**：2026-07-23
> **承接关系**：阶段 0-7 全部收口。Wave 7 按整合方案 §10 阶段 8 的 12 项任务 + 4 项验收标准，**形成可重复演示、可测试、可继续扩展的学习版成果**。
> **承接方案 13 章 5 类演示用例**：
>   1. 编程 Agent（修 bug + 跑测试）—— 部分（Wave 5.2 T12）
>   2. 知识库 Agent（问内部政策）—— 部分（Wave 4 RAG）
>   3. 数据库 Agent（自然语言问数）—— 部分（Wave 4 DB Adapter）
>   4. 前端操作 Agent（找 GeoJSON + 加载）—— **0%**
>   5. 综合多能力任务（政策 + 外部 + 图表）—— **0%**

---

## 一、目标

按整合方案阶段 8 的 12 项任务 + 4 项验收标准，从"组件齐全"升级为"开箱可演示 + 可测试 + 可继续扩展"：

```
现有（Wave 0-6.1）
  1395 passed / 235 files / 单组件齐全 / 无统一启动脚本
新增（Wave 7）
  Docker Compose 三模式（minimal / web / full）
  统一启动脚本（scripts/start.sh）
  5 演示用例脚本化（可重跑 + 报告）
  故障注入 / 性能基线 / 安全基线套件
  README + 架构图 + 开发指南 + 演示手册
  硬编码凭据清理（.env 提交了真 KEY，要清）
  "已迁移/未迁移/后续计划"清单
```

**核心交付**：
- `docker-compose.yml` 三模式（minimal / web / full profile）
- `scripts/start.sh` + `scripts/run_demos.sh` + `scripts/health_check.sh`
- `demos/` 5 演示用例 + fixture
- `tests/integration/test_failure_injection.py`（5 场景）
- `tests/performance/test_benchmarks.py`（3 模式）
- `tests/security/test_security_baseline.py`（4 场景）
- `README.md` + `RUNBOOK.md` + `docs/architecture/` + `docs/development/` + `docs/demo/` + `MIGRATION.md`
- `.env.example` 完整 + git history 清掉真 KEY（用 `git filter-repo` 或 BFG）

---

## 二、范围

### 2.1 必做（Wave 7 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| K1 | Docker Compose 三模式 + 启动脚本 + 配置 + 凭据清理 | 2-3 天 | `docker-compose.yml` + `scripts/start.sh` + `.env.example` + 凭据清理 |
| K2 | 5 演示用例脚本化 | 3-4 天 | `demos/demo1-5.py` + `demos/fixtures/` + `scripts/run_demos.sh` |
| K3 | 故障注入 + 性能基线 + 安全基线 | 2-3 天 | `tests/{integration,performance,security}/` 12+ case |
| K4 | README + 架构图 + 开发指南 + 演示手册 + 迁移清单 | 2-3 天 | `README.md` + `RUNBOOK.md` + `docs/{architecture,development,demo}/` + `MIGRATION.md` |
| 主控 | 集成 + 全量验证 + 收口 | 1-2 天 | 集成 commit + 收口记录 |

**总估时**：10-15 天，4 WT 并行 + 集成

### 2.2 阶段 8 任务列表 vs 实际拆分

整合方案阶段 8 12 项任务：

| 任务 | 状态 | 拆分到哪个 WT |
|---|---|---|
| ❌ 编写统一启动脚本 / Docker Compose | **K1** | K1 docker-compose.yml + scripts/start.sh |
| ❌ 提供最小模式（Core + CLI/TUI） | **K1** | K1 minimal profile |
| ❌ 提供 Web 模式（Core + Gateway + Chatbox） | **K1** | K1 web profile |
| ❌ 提供完整模式（+ Vector Memory + Redis + Evaluation） | **K1** | K1 full profile |
| ❌ 建立示例配置，不提交真实密钥 | **K1** | K1 .env.example + git history 清理 |
| ❌ 清理 aigroup 迁移代码中的硬编码 | **K1** | K1 git grep 检查 + replace |
| ❌ 完成五类演示用例 | **K2** | K2 demos/demo1-5.py |
| ❌ 完成故障注入（5 场景） | **K3** | K3 test_failure_injection.py |
| ❌ 完成性能基线（3 模式） | **K3** | K3 test_benchmarks.py |
| ❌ 完成安全基线（4 场景） | **K3** | K3 test_security_baseline.py |
| ❌ 更新 README/架构图/开发指南/演示手册 | **K4** | K4 docs/ |
| ❌ 形成"已迁移/未迁移/后续计划"清单 | **K4** | K4 MIGRATION.md |

### 2.3 验收标准 vs 实际

| 验收 | 拆到哪个 WT 验证 |
|---|---|
| 新环境能够按照文档启动 | K1 + K4（README + Docker Compose + start.sh） |
| 五个核心演示用例全部通过 | K2（5 demos 跑通） |
| CLI/TUI 原能力不回退 | 主控（uv run kivi / kivi-tui ping / version） |
| Web/业务 Tool/多 Agent/记忆/评估形成完整闭环 | K2（demo 5 跨所有组件）+ K3（端到端） |

---

## 三、4 个 WT 详细设计

### WT-K1: Docker Compose 三模式 + 启动脚本 + 凭据清理

**目标**：3 个 profile + 统一启动 + 完整配置 + 凭据清干净

**代码位置**：
- `docker-compose.yml`（替换现有）：3 profile 标记
  - `minimal`：只起 core daemon（无外部依赖）
  - `web`：+ gateway + chatbox
  - `full`：+ elasticsearch + redis + evaluation exporter
- `docker-compose.test.yml`（保留 Wave 4 的 pg test）
- `scripts/start.sh`：按 `--mode minimal|web|full` 启对应 services
- `scripts/health_check.sh`：curl 验证 core / gateway / ES / redis 状态
- `scripts/stop.sh`：docker compose down
- `.env.example`（重写）：完整覆盖 core / llm / gateway / memory / embedding / openai / es / redis / logging
- `.gitignore`：加 `.env` 强制不提交
- `pyproject.toml`：scripts 段加 `kivi-start` / `kivi-stop` / `kivi-health` 命令

**凭据清理**：
- `git grep -E "sk-(ant-|[a-zA-Z0-9]{20,})"` 全仓库扫
- 发现 `.env` 含真 `ANTHROPIC_API_KEY=sk-b4f933c2...` —— 立刻清掉
- 用 `git filter-repo` 从历史删除 `.env`（或者 BFG Repo-Cleaner）
- 加 pre-commit hook 检查 `.env` 不被追踪

**测试**：
- `tests/integration/test_docker_compose_minimal.sh`（启 minimal，curl /health 200）
- `tests/integration/test_docker_compose_web.sh`（启 web，curl /api/dashboard/summary）
- `tests/integration/test_docker_compose_full.sh`（启 full，curl ES /_cluster/health）
- `tests/unit/test_env_example.py`（验证 .env.example 包含所有必要键 + 不含真值）

**commit 规划**：4-5 commit
1. `chore(env): .env.example 完整覆盖 core/llm/gateway/memory/embedding/openai/es/redis`
2. `feat(docker): docker-compose.yml 三模式（minimal/web/full）+ healthcheck`
3. `feat(scripts): start.sh / stop.sh / health_check.sh（按 --mode 启停）`
4. `chore(security): .env 加 .gitignore + git filter-repo 清理历史真 KEY`
5. `test(integration): docker-compose 三模式 + .env.example 完整性测试`

### WT-K2: 5 演示用例脚本化

**目标**：5 个 demo 脚本可重跑，每个输出明确 pass/fail 报告

**代码位置**：
- `demos/__init__.py`
- `demos/demo1_coding.py`：编程 Agent（修 bug + 跑 pytest，用 Wave 6.1 T12）
- `demos/demo2_rag.py`：知识库 Agent（问内部政策，用 Wave 4 RAG HTTP）
- `demos/demo3_database.py`：数据库 Agent（自然语言问数，用 Wave 4 DB Adapter）
- `demos/demo4_frontend_map.py`：前端操作 Agent（找 GeoJSON + 加载地图）—— **新做 frontend_tool agent + 地图 Tool**
- `demos/demo5_multi_agent.py`：综合多能力（政策 + 外部 + 图表 + 多 agent 协作）
- `demos/fixtures/`：每个 demo 1 个 fixture
  - `demo1_coding_fixture.py`（add 函数 + 故意写错）
  - `demo2_rag_fixture.txt`（3 篇政策文档）
  - `demo3_database_fixture.sql`（orders 表 + 100 行）
  - `demo4_geojson_fixture.json`（3 个公开 GeoJSON URL）
  - `demo5_multi_task_input.json`
- `demos/base.py`：`DemoBase` 类（统一 setup / run / teardown / report）
- `scripts/run_demos.sh`：按顺序跑 5 demo，输出汇总报告

**frontend_tool + 地图 Tool 新做内容**：
- `src/kivi_agent/core/tools/builtin/map_load.py`：`MapLoadTool`（`BaseTool`）
  - 输入：geojson_url（公开 URL）
  - 输出：loaded_features_count / bbox
  - 副作用：通过 WebSocket 推 `map.geojson_loaded` 事件
- `src/kivi_agent/core/agents/builtin/business/frontend_tool.toml`：新 business profile
- 前端 Web Chat 加 `MapView.vue`（用 vue3-openlayers 或 Leaflet 渲染 GeoJSON）

**commit 规划**：5-6 commit
1. `feat(demos): DemoBase + 5 demo 脚本 + fixtures`
2. `feat(tools): MapLoadTool（前端地图 Tool）+ 业务 Profile frontend_tool`
3. `feat(agents): frontend_tool 业务 profile + 集成 BusinessRouter`
4. `feat(scripts): run_demos.sh 顺序跑 5 demo + 汇总报告`
5. `feat(web-chat): MapView.vue 渲染 GeoJSON（vue3-openlayers）`
6. `test(demos): 5 demo 跑通测试（mock LLM 注入）+ 端到端 1 case`

### WT-K3: 故障注入 + 性能基线 + 安全基线

**目标**：3 类共 12 case 测试套件

**代码位置**：
- `tests/integration/test_failure_injection.py`（5 场景）：
  - `test_model_failure`：LLM provider 抛异常，主任务不挂
  - `test_tool_timeout`：Tool 调用超时，重试 3 次后 fallback
  - `test_subagent_failure`：子 Agent 失败，父任务降级
  - `test_ws_disconnect`：WebSocket 断线，重连 + replay
  - `test_cancellation`：用户取消，资源清理
- `tests/performance/test_benchmarks.py`（3 模式）：
  - `test_single_agent_latency`：单 Agent 跑 5 任务，p50 / p95 延迟
  - `test_serial_multi_agent`：串行多 Agent（5 子任务），总延迟 = sum(p50)
  - `test_parallel_team`：并行 Team（5 子任务并发），总延迟 ≈ max(p50)
  - 输出 `reports/benchmark_*.json` 报告
- `tests/security/test_security_baseline.py`（4 场景）：
  - `test_path_traversal`：尝试 `../../../etc/passwd`，应被拒绝
  - `test_dangerous_bash`：尝试 `rm -rf /`，应被权限系统拒绝
  - `test_skill_script_isolation`：Skill 脚本不能访问 ~/.ssh
  - `test_frontend_tool_spoofing`：伪造 request_id 的前端 Tool 调用应被拒绝
- `tests/conftest_perf.py`：性能基线公共 fixture
- `tests/conftest_security.py`：安全基线公共 fixture

**commit 规划**：4-5 commit
1. `feat(test): 故障注入 5 场景（model / tool timeout / subagent / ws / cancel）`
2. `feat(test): 性能基线 3 模式（single / serial / parallel）+ reports/ 输出`
3. `feat(test): 安全基线 4 场景（path / bash / skill / frontend spoofing）`
4. `chore(test): conftest 拆分 perf / security 公共 fixture`

### WT-K4: README + 架构图 + 开发指南 + 演示手册 + 迁移清单

**目标**：4 类文档齐全，新人按 README 即可启动 + 跑 5 demo + 贡献

**代码位置**：
- `README.md`（重写）：项目介绍 / 环境要求 / 快速开始（minimal / web / full 三模式）/ 5 demo 链接 / 文档索引
- `RUNBOOK.md`（新建）：详细操作参考（配置 / 启停 / 调试 / 故障排查）
- `docs/architecture/architecture.md`：整体架构 + 模块说明（mermaid 图）
- `docs/architecture/sequence-diagrams/`：核心流程 sequence 图（agent.run / multi_agent / eval / memory / dashboard）
- `docs/architecture/data-flow.md`：数据流（user input → LLM → tool → memory → response）
- `docs/development/contributing.md`：贡献指南（代码风格 / 测试 / PR 流程 / commit 规范）
- `docs/development/modules.md`：模块说明（按目录分章节）
- `docs/demo/demo1_coding.md` / `demo2_rag.md` / `demo3_database.md` / `demo4_frontend_map.md` / `demo5_multi_agent.md`：5 演示手册（输入 / 期望输出 / 截图位 / 复现命令）
- `MIGRATION.md`：已迁移 / 未迁移 / 后续计划清单
  - 已迁移：kama/kivi-agent + aigroup 哪些能力已合并到 kivi-agent
  - 未迁移：aigroup 里哪些能力没合并（frontend_tool / Redis Streams / Cross-Encoder 等）
  - 后续计划：Wave 8 候选（生产部署 / 真实 LLM 端到端 / 多租户）

**commit 规划**：4-5 commit
1. `docs: README.md 重写（按 stage 8 验收：可启动 / 5 demo / 不退化）`
2. `docs: RUNBOOK.md + docs/architecture/architecture.md + mermaid 图`
3. `docs: docs/development/contributing.md + modules.md`
4. `docs: docs/demo/ 5 演示手册`
5. `docs: MIGRATION.md（已迁移/未迁移/后续计划）`

---

## 四、4 个 WT 集成顺序

```
K1 (docker + 凭据清理) ─┐
K2 (5 demos)            ─┼─→ 主控集成（4 merge + 收口）
K3 (故障/性能/安全基线) ─┤
K4 (文档)               ─┘
```

**主控集成顺序**：
1. cherry-pick / rebase K1 → K2 → K3 → K4 到 `integration/aigroup-wave7`
2. 集成期修复
3. **关键：先 K1 跑 3 mode 端到端，再 K2 跑 5 demo，再 K3 跑基线，最后 K4 文档**
4. **凭据清理要在 K1 集成后立即验证**（git log 检查历史无真 KEY）
5. 全量验证：pytest / mypy / ruff / 前端 type-check/test/lint/build / 5 demo / 3 mode docker compose up
6. 收口记录
7. 合并 main + 推 GitHub + 清理 worktree

---

## 五、风险与边界

| 风险 | 缓解 |
|---|---|
| **历史 .env 含真 KEY**（已发现 `sk-b4f933c2...`）| K1 必做 git filter-repo 清理 + BFG 兜底；K4 README 加安全声明 |
| K2 demo 4 地图 Tool 涉及新业务 Tool + 前端组件 | demo 4 标"可选"（如果时间不够允许 demo 1-3-5 通过验收）|
| K3 性能基线波动 | 多次跑取中位数；不卡绝对值，卡相对比（parallel ≈ single / 5）|
| K3 安全基线需要越权能力 | 用 mock attacker 模拟，不真攻击；K3 文档明确"非真实攻击测试" |
| K1 Docker Compose full profile 启 ES 占 1GB | CI 不跑 full（用 env guard），只跑 minimal / web |
| K2 demo 5 跨所有组件（multi-agent + RAG + DB + chart）| 拆成 3-4 子步骤，每步可独立验证 |

---

## 六、收口判定

- [ ] 后端 pytest 全绿（基线 1395 + Wave 7 新增 ≥ 20 case）
- [ ] mypy 0 / ≥ 240 files（235 + 5-10 新文件）
- [ ] ruff 与 Wave 6.1 收口基线持平（45，**Wave 7 新增 0**）
- [ ] 前端 type-check / test / lint / build 全绿（基线 178 + Wave 7 新增 ≥ 5）
- [ ] **Docker Compose 三模式可启**（minimal / web / full，curl 验证）
- [ ] **5 演示用例全过**（demo1-5 端到端跑通，报告输出）
- [ ] **故障注入 5 场景全过**（model / tool timeout / subagent / ws / cancel）
- [ ] **性能基线 3 模式**报告输出（reports/benchmark_*.json）
- [ ] **安全基线 4 场景**全过（path / bash / skill / frontend spoofing）
- [ ] **历史 .env 真 KEY 已清**（git filter-repo 验证）
- [ ] **README + RUNBOOK + 架构图 + 5 demo 手册 + MIGRATION** 完整
- [ ] 4 个 Wave 7 worktree 合并后清理
- [ ] Ruff pre-existing 45 项基线（不阻塞 Wave 7 关闭）

---

## 七、Wave 7 → 后续

按整合方案 14 章"主要风险与控制措施"和我们的现状，Wave 7 完成后可能的下一波：

- **Wave 8.1**：生产部署（k8s manifest / Helm / TLS / 多副本）
- **Wave 8.2**：真实 LLM 端到端（无 ANTHROPIC_API_KEY 限制的完整 E2E）
- **Wave 8.3**：多租户隔离（authn / authz / quota）
- **Wave 8.4**：Cross-Encoder Reranker 升级 + Redis Streams Exporter

Wave 7 完成后，kivi-agent 达到整合方案阶段 8 验收标准：5 演示用例可重跑、3 模式可启、4 类基线全过、文档齐全。后续是否进入 Wave 8 取决于"对内演示 / 对外开源 / 公司生产"的最终方向（之前问过用户，还没收到答案）。
