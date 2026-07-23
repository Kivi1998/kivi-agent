# aigroup Wave 5.1：Evaluation 最小闭环 + Trace Dashboard

> **基线**：`main @ e352ac6`（aigroup Wave 4 收官，999 passed / 187 files / Adapter 架构）
> **日期**：2026-07-23
> **承接关系**：用户 2026-07-23 选定 "Wave 5.1 Eval 基础 + Dashboard"；T11/T12 高级指标留 Wave 5.2
> **目标**：从"功能很多的 Demo"升级为"可展示 Agent 工程质量的系统"——Evaluation、Observability、Trace、性能指标

---

## 一、目标

让 kivi-agent 从"Agent 能运行"进入"**Agent 可测量、可解释、可展示**"：

```
数据集 (JSONL)
  ↓
批量运行 (kivi-eval run)
  ↓
Judge 评估
  ↓
指标计算
  ↓
Trace Dashboard (Vue 3)
```

**核心交付**：
- 评测数据集 schema + 批量运行 CLI
- 7 个基础指标：任务成功率 / 路由正确率 / Tool 选择正确率 / RAG 引用准确率 / 延迟 / Token / 成本
- Trace Dashboard 后端 API（FastAPI）
- Trace Dashboard 前端（Vue 3 + 5 个 widget）
- 演示数据集 + 集成 + 文档

---

## 二、范围

### 2.1 必做（Wave 5.1 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| G1 | 评测数据集 schema + 批量运行 CLI + Judge 集成 | 3-4 天 | `src/kivi_agent/eval/dataset.py` + `cli/eval.py` + `tests/` |
| G2 | 指标计算引擎（7 指标） | 3-4 天 | `src/kivi_agent/eval/metrics/` + 测试 |
| G3 | Trace Dashboard 后端 API | 2-3 天 | `src/kivi_agent/gateway/dashboard.py` + 测试 |
| G4 | Trace Dashboard 前端（Vue 3 + 5 widget） | 3-4 天 | `apps/web-chat/src/views/Dashboard.vue` + components |
| 主控 | 演示数据集 + 集成 + 文档 + 4 截图 | 2-3 天 | `docs/eval-demos/` + 集成 commit |

**总估时**：13-18 天，4 WT 并行 + 集成

### 2.2 7 个基础指标（Wave 5.1 必做）

| 指标 | 公式 | 数据来源 |
|---|---|---|
| 任务成功率 | `成功 case / 总 case` | run.finished.status |
| 路由正确率 | `路由匹配 / 总 case` | RouteDecision vs dataset.expected_route |
| Tool 选择正确率 | `正确 tool 名次数 / 总 tool 调用次数` | tool.call_started vs dataset.expected_tools |
| RAG 引用准确率 | `正确引用数 / 总引用数` | rag.sources_cited vs dataset.expected_sources |
| 平均延迟 | `Σ run.finished.ts - run.started.ts / case` | run.started/finished |
| 总 Token | `Σ llm.usage.input_tokens + output_tokens` | llm.usage |
| 总成本 | `Σ (input * price_in + output * price_out)` | llm.usage + price table |

### 2.3 明确不做（推迟到 Wave 5.2 / Wave 6 / 最后）

| 项 | 推迟理由 | 后续 |
|---|---|---|
| T11 多 Agent 指标（并发 / 等待 / 子任务成功率 / 汇总失败率） | 用户拆段 | Wave 5.2 |
| T12 编程 Agent 指标（测试通过率 / 补丁应用率 / 回滚次数） | 用户拆段 | Wave 5.2 |
| Vector Memory | 等真实 RAG 使用一段时间后再做 | Wave 6 |
| 真实 rag-kb 服务接入 | 用户"不接生产" | 最后 |
| 登录 / 租户 / SSO | 企业产品化 | 最后 |
| 文档 / 部署 / 演示收口 | 项目尾声 | 最后 |

---

## 三、4 个 WT 拆分

### WT-G1 评测数据集 schema + 批量运行 CLI + Judge 集成

**目标**：定义评测数据集格式 + CLI 工具批量跑评测 + 复用 Wave 1 E 包的 Judge。

**任务**：
- `src/kivi_agent/eval/dataset.py`：EvalCase / EvalDataset 数据类 + JSONL 加载
  - EvalCase：id / goal / expected_route / expected_tools / expected_sources / expected_answer / tags
  - EvalDataset：list[EvalCase] + 按 tag 过滤
- `src/kivi_agent/eval/runner.py`：EvalRunner 类
  - `run(case: EvalCase) -> EvalResult`
  - 复用现有 AgentRuntime + BusinessRouter + 6 业务 Tool
  - 收集 run.started/finished + tool.call_started/finished + rag.sources_cited + chart.rendered 事件
  - 调 Judge（Wave 1 E 包）评分 answer
- `src/kivi_agent/cli/eval.py`：CLI
  - `kivi-eval run --dataset <path> --output <path> --tags <tag>` 批量跑
  - `kivi-eval summary <run-id>` 跑汇总
- 单元 + 集成测试

**交付文件**：
- `src/kivi_agent/eval/__init__.py`（新）
- `src/kivi_agent/eval/dataset.py`（新，~120 行）
- `src/kivi_agent/eval/runner.py`（新，~150 行）
- `src/kivi_agent/eval/judge.py`（新，~80 行，复用 Wave 1 E 包）
- `src/kivi_agent/eval/result.py`（新，~60 行，EvalResult 数据类）
- `src/kivi_agent/cli/eval.py`（新，~80 行）
- `tests/unit/test_eval_dataset.py`（新，~100 行，4 测试）
- `tests/unit/test_eval_runner.py`（新，~120 行，4 测试）
- `tests/integration/test_eval_run.py`（新，~150 行，3 场景）

### WT-G2 指标计算引擎（7 指标）

**目标**：从 EvalResult 列表计算 7 个指标 + 输出 JSON。

**任务**：
- `src/kivi_agent/eval/metrics/base.py`：Metric 抽象基类
- `src/kivi_agent/eval/metrics/task_success.py`：任务成功率
- `src/kivi_agent/eval/metrics/route_accuracy.py`：路由正确率
- `src/kivi_agent/eval/metrics/tool_accuracy.py`：Tool 选择正确率
- `src/kivi_agent/eval/metrics/rag_citation.py`：RAG 引用准确率
- `src/kivi_agent/eval/metrics/latency.py`：平均延迟
- `src/kivi_agent/eval/metrics/token.py`：总 Token
- `src/kivi_agent/eval/metrics/cost.py`：总成本
- `src/kivi_agent/eval/metrics/report.py`：MetricsReport 汇总 + JSON 输出
- 价格表：`config.example.toml` 增 `[pricing]` section（claude-sonnet / gpt-4 等）
- 单元测试（每个指标独立测试）

**交付文件**：
- `src/kivi_agent/eval/metrics/__init__.py`（新）
- `src/kivi_agent/eval/metrics/base.py`（新，~40 行）
- 7 个指标文件（每个 ~50 行）
- `src/kivi_agent/eval/metrics/report.py`（新，~100 行）
- `tests/unit/test_metrics.py`（新，~250 行，每指标 2-3 测试）

### WT-G3 Trace Dashboard 后端 API

**目标**：FastAPI 暴露 Dashboard 数据 API + 复用 Wave 1 TraceEmitter。

**任务**：
- `src/kivi_agent/gateway/dashboard.py`：APIRouter
  - `GET /api/dashboard/summary`：总览（case 总数 / 成功率 / 平均延迟 / 总 Token / 总成本）
  - `GET /api/dashboard/runs?limit=20&offset=0`：评测运行列表
  - `GET /api/dashboard/runs/{run_id}`：单个 run 详情
  - `GET /api/dashboard/metrics/{run_id}`：单 run 的 7 指标
  - `GET /api/dashboard/traces/{run_id}?case_id=xxx`：单 case 的事件流（llm/tool/rag/chart）
- 数据存储：复用 `~/.kama/traces/daemon.jsonl`（Wave 1 既有） + 新增 `~/.kama/eval/results.jsonl`（Wave 5.1 引入）
- 集成 gateway/main.py 注册路由
- 单元 + 集成测试

**交付文件**：
- `src/kivi_agent/gateway/dashboard.py`（新，~180 行）
- `src/kivi_agent/eval/store.py`（新，~100 行，EvalResultStore 持久化）
- `tests/unit/test_dashboard_api.py`（新，~200 行，6+ 测试）
- `tests/integration/test_dashboard_e2e.py`（新，~120 行，3 场景）

### WT-G4 Trace Dashboard 前端（Vue 3 + 5 widget）

**目标**：在 Wave 3 已有 Vue 3 Chat 前端基础上，新增 Dashboard 视图 + 5 个 widget。

**任务**：
- 路由：`/dashboard` + `/dashboard/runs/:runId` + `/dashboard/runs/:runId/cases/:caseId`
- 5 个 widget：
  - `SummaryCard`：4 个 metric 大卡（成功率 / 平均延迟 / 总 Token / 总成本）
  - `RunsList`：评测运行列表（按时间倒序）
  - `MetricsBar`：单 run 的 7 指标条形图（用 Wave 3 ChartWidget 同样的 ECharts）
  - `TraceTimeline`：单 case 的事件流时间轴（llm / tool / rag / chart）
  - `CaseTable`：单 run 的 case 列表（通过/失败 + 指标）
- API 客户端：`src/api/dashboard.ts`
- 复用 Wave 3 的 `useWebSocket`（增量事件流）
- 单元测试 + Storybook 可选

**交付文件**：
- `apps/web-chat/src/views/Dashboard.vue`（新，~200 行）
- `apps/web-chat/src/views/DashboardRunDetail.vue`（新，~200 行）
- `apps/web-chat/src/views/DashboardCaseDetail.vue`（新，~150 行）
- `apps/web-chat/src/components/SummaryCard.vue`（新，~80 行）
- `apps/web-chat/src/components/RunsList.vue`（新，~120 行）
- `apps/web-chat/src/components/MetricsBar.vue`（新，~150 行）
- `apps/web-chat/src/components/TraceTimeline.vue`（新，~180 行）
- `apps/web-chat/src/components/CaseTable.vue`（新，~150 行）
- `apps/web-chat/src/api/dashboard.ts`（新，~100 行）
- 各 .spec.ts 测试
- router.ts 加 3 个路由

### WT-G5（主控）：演示数据集 + 集成 + 文档

**目标**：演示数据集 + 集成 4 WT + 文档 + 4 截图。

**任务**：
- 演示数据集：`docs/eval-demos/basic-routing-10cases.jsonl`（10 个 case 覆盖 5 个业务 Profile）
- 集成 4 个 WT（merge + 冲突处理）
- 跑全量测试 + 修 ruff
- 文档：
  - `docs/superpowers/plans/2026-07-23-aigroup-wave5-1-eval-basics.md`（本文件）
  - `docs/eval-demos/README.md`（演示步骤）
  - `docs/迁移记录/最小闭环验收记录.md` 新增 Wave 5.1 章节
- 4 张截图（Dashboard 主页 / Run 详情 / Case 时间轴 / Metrics 条形图）

---

## 四、目录结构

### 新增

```
src/kivi_agent/eval/                          # WT-G1 + WT-G2
  __init__.py
  dataset.py
  runner.py
  judge.py
  result.py
  store.py                                    # WT-G3
  metrics/
    __init__.py
    base.py
    task_success.py
    route_accuracy.py
    tool_accuracy.py
    rag_citation.py
    latency.py
    token.py
    cost.py
    report.py

src/kivi_agent/cli/eval.py                    # WT-G1

src/kivi_agent/gateway/dashboard.py           # WT-G3

apps/web-chat/src/views/                      # WT-G4
  Dashboard.vue
  DashboardRunDetail.vue
  DashboardCaseDetail.vue

apps/web-chat/src/components/                 # WT-G4
  SummaryCard.vue
  RunsList.vue
  MetricsBar.vue
  TraceTimeline.vue
  CaseTable.vue

apps/web-chat/src/api/dashboard.ts            # WT-G4

docs/eval-demos/                              # WT-G5
  basic-routing-10cases.jsonl
  README.md
  screenshots/
    dashboard-overview.png
    run-detail.png
    case-timeline.png
    metrics-bar.png
```

### 修改

```
src/kivi_agent/gateway/main.py                # WT-G3 注册 dashboard 路由
pyproject.toml                                # WT-G1 + WT-G2 依赖（pytest-click 等）
config.example.toml                           # WT-G2 加 [pricing] section
docs/contracts/v1.md                          # 不改（v1 冻结）；Eval 不引入新事件 / Tool 名
WIRE_PROTOCOL.md                              # 不变（Eval 内部用 v1 §5.2.1 6 事件）
docs/迁移记录/最小闭环验收记录.md              # 新增 Wave 5.1 章节
```

---

## 五、Wave 5.1 实施流程

按 Wave 1-4 成熟模式：

1. **4 个 worktree 并行**（`integration/aigroup-wave5-1-{dataset,metrics,api,frontend}`）
2. **4 个 sub-agent 并行**（每个 2-4 天工作量）
3. **主控集成**：
   - 建 `integration/aigroup-wave5-1` 分支
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
| 评测数据集 schema 与 Judge 期望不一致 | WT-G1 显式定义 EvalCase 字段；Judge 只用 expected_answer + expected_sources |
| 7 指标定义歧义（什么是"正确 tool"） | WT-G2 显式定义每指标公式 + 边界 case；参考 Wave 1 E 报告 §7.4 指标章节 |
| Dashboard 后端 API 与前端契约 | WT-G3 先写 API 文档；WT-G4 严格按 TypeScript 类型反推 |
| 真实评测跑太慢 | 数据集默认 10 case；批量运行支持并发（asyncio.gather） |
| 价格表不在评测运行时给 | config.example.toml 增 [pricing] section（默认值 + 注释指引） |
| Trace 数据量大 | Dashboard 默认 limit=20，分页；事件流按 case_id 索引 |

---

## 七、Wave 5.1 关闭判定

- [ ] 4 个子包全部合入 `integration/aigroup-wave5-1` → `main`
- [ ] 后端测试 999+N passed / 0 failed（N 待统计）
- [ ] 前端 55+N passed / 0 failed（N 待统计）
- [ ] mypy 0 issue
- [ ] 前端 type-check 0 / lint 0 / build success
- [ ] ruff 0 新增
- [ ] 评测数据集 schema + JSONL 加载 + 案例覆盖 5 Profile
- [ ] 批量运行 CLI `kivi-eval run` 跑通
- [ ] 7 个指标全部实现 + 单元测试
- [ ] Dashboard 后端 API 5 个端点（summary / runs / run detail / metrics / traces）
- [ ] Dashboard 前端 5 个 widget（SummaryCard / RunsList / MetricsBar / TraceTimeline / CaseTable）
- [ ] 演示数据集 10 case 跑通
- [ ] 4 张 Dashboard 截图
- [ ] 文档同步：最小闭环验收记录新增 Wave 5.1 章节
- [ ] v1 契约未变（Eval 不引入新事件 / Tool 名 / 字段）

---

## 八、Wave 5.2 / 6 / 最后 候选

| 阶段 | 内容 | 估时 |
|---|---|---|
| Wave 5.2 | T11 多 Agent 指标 + T12 编程 Agent 指标 | 15-20 天 |
| Wave 6 | Vector Memory Backend（等真实 RAG 使用一段时间后再做） | 20+ 天 |
| 最后 | 真实 rag-kb 服务接入 + 文档 + 部署 + 演示收口 | 30+ 天 |

**用户推荐路线**：
> Wave 5.1 → 5.2 → Wave 6 → 最后

---

## 九、参考

- 方案：`kivi-agent与aigroup整合实施方案.md` §5 阶段 7（Observability 与 Evaluation 平台）
- v1 契约：`docs/contracts/v1.md`（不变）
- Wave 1 E 报告：`docs/migration/evaluation-quality-analysis.md`（Wave 1 推迟的 T11/T12）
- Wave 4 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 4" 章节
- Wave 3 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 3" 章节
- 现状：
  - `src/kivi_agent/evaluation/`（Wave 1 E 包的 EvalEmitter / Judge）
  - `src/kivi_agent/gateway/main.py`（Wave 1 D 包 + Wave 3 E1 路由）
  - `apps/web-chat/`（Wave 3 Vue 3 前端）
  - `~/.kama/traces/daemon.jsonl`（Wave 1 Trace 数据）

---

**Wave 5.1 起草**：Mavis（主控 Agent）
**用户批准**：2026-07-23 "选 B：Wave 5.1 Eval 基础 + Dashboard（先不做 5.2）"
**下一步**：创建 4 个 worktree + 启动 4 个 sub-agent（WT-G1/G2/G3/G4 并行）
