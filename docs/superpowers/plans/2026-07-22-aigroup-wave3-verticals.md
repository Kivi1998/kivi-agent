# aigroup Wave 3：垂直能力（待用户选定方向）

> **基线**：`main @ 3d7bf94`（aigroup Wave 2 已收官，918 passed / 170 files mypy 0 / ruff 0 新增）
> **日期**：2026-07-22
> **承接关系**：方案 §8.5 Wave 3 = 方案 §5 阶段 5（Web Gateway/Chatbox）+ 阶段 6（Vector Memory）+ 阶段 7（Eval Dashboard）三选一/多选
> **状态**：**待用户选方向**

---

## 一、3 个候选阶段

### 1.1 阶段 5：Web Gateway、Chatbox 与前端工具（6-9 天）

**目标**：为 kivi-agent 增加 Web 产品入口，同时保留 Core Daemon 作为唯一运行时。

**kivi 现状**（Wave 1 D 包已完成）：
- ✅ `AgentRuntime` Protocol + `RuntimeAdapter`（SocketClient 桥接）
- ✅ `WebSocketBridge`（per-client queue 事件桥接）
- ✅ FastAPI 6 路由骨架（实际只"骨架和部分真实桥接"）
- ✅ SessionCancel 命令组 + 集成测试

**未做**：
- ❌ 真实业务事件经 WebSocket 透传（Token / Thinking / Tool / Skill / Subagent / Team / Permission）
- ❌ Chatbox UI（diit-chatbox 迁移）
- ❌ RAG 引用溯源 + ECharts 图表前端渲染
- ❌ 动态 Tool Bridge（前端调 Tool，含 request_id 关联）
- ❌ Web 断线 / 重连 / 取消任务
- ❌ Web 端权限审批界面

**多 worktree 拆分建议**：

| WT | 范围 | 估时 | 依赖 |
|---|---|---|---|
| WT-E1 Web Events | WebSocket 业务事件透传（6 类 v1 事件 + SessionCancel）+ 心跳 / 重连 | 3 天 | 无 |
| WT-E2 Chatbox UI | 迁移 diit-chatbox 基础 UI（Vue 3）+ RAG 引用 + ECharts 渲染 | 3-4 天 | WT-E1 |
| WT-E3 Frontend Tool Bridge | 动态 Tool 调用 + request_id 关联 + 权限审批 UI | 2-3 天 | WT-E1 |
| 主控集成 | 合并 3 WT + E2E（Web 断线 / 重连 / 取消） + 文档 | 2 天 | 全部 |

**总估时**：10-12 天，3 WT 并行 + 集成

### 1.2 阶段 6：长期记忆与持久化适配（4-7 天）

**目标**：保留本地透明记忆，同时引入 aigroup 的语义检索与审计能力。

**kivi 现状**（Wave 1 C 包已完成）：
- ✅ `MemoryBackend` Protocol
- ✅ `LocalMemoryBackend` Mock 实现
- ✅ 6 业务 Tool 之一 `memory_save` / `memory_recall` Mock

**未做**：
- ❌ `VectorMemoryBackend` 真实实现（需 ES / pgvector 外部依赖）
- ❌ Embedding / 候选召回 / Reranker 精排
- ❌ 记忆类型 / 重要度 / 状态 / 过期时间
- ❌ 敏感信息过滤 / 语义去重 / 冲突归档
- ❌ 记忆审计事件
- ❌ 按问题召回（替代"全部注入上下文"）

**多 worktree 拆分建议**：

| WT | 范围 | 估时 | 依赖 |
|---|---|---|---|
| WT-F1 Vector Backend | `VectorMemoryBackend` 真实实现 + Embedding mock | 2-3 天 | 无 |
| WT-F2 Memory Quality | 重要度 / 过期 / 去重 / 冲突归档 + 审计事件 | 2-3 天 | WT-F1 |
| WT-F3 Recall Refactor | 改 `memory_recall` 走"按问题召回"而非全注入 | 1-2 天 | WT-F1 |
| 主控集成 | 合并 3 WT + E2E + 文档 | 1-2 天 | 全部 |

**总估时**：6-10 天

**风险**：
- 外部依赖（ES / pgvector）需要 Docker / 本地安装
- Embedding 真实化需 API key
- v1 §7.2 demo 定位：可能先 Mock，等真实化推到 Wave 4+

### 1.3 阶段 7：Observability 与 Evaluation 平台（5-8 天）

**目标**：将 kivi-agent 本地 Trace 提升为可聚合、可评测的平台级能力。

**kivi 现状**（Wave 1 E 包已完成）：
- ✅ `EvalEmitter` 骨架
- ✅ `Judge` 修复版（必填 `expected_answer` + `reference_context`）
- ✅ `schema_version` 守门单测
- ✅ 13 契约测试 0 skipped
- ❌ E 报告 §T11/T12 推迟到 Wave 2（实际没做）

**未做**：
- ❌ 统一 Trace Schema v1
- ❌ Redis Streams Exporter
- ❌ Evaluation Consumer
- ❌ Dashboard / Trace / Failures / Metrics 页面（前端）
- ❌ 评测数据集 / 评测批次
- ❌ 路由正确性 / 工具选择正确性 / 引用准确率指标
- ❌ 多 Agent 指标（并发数 / 等待时间 / 子任务成功率）
- ❌ 编程 Agent 指标（测试通过率 / 补丁应用率 / 回滚次数）

**多 worktree 拆分建议**：

| WT | 范围 | 估时 | 依赖 |
|---|---|---|---|
| WT-G1 Trace Schema | 统一 Trace Schema v1 + JSONL TraceWriter 扩展 + Redis Streams Exporter | 2 天 | 无 |
| WT-G2 Eval Service | Evaluation Consumer + 评测数据集 / 批次 + Judge 集成 | 2-3 天 | WT-G1 |
| WT-G3 Dashboard | Vue 3 Dashboard（Trace / Failures / Metrics 三页） | 3-4 天 | WT-G1 |
| WT-G4 Metrics | 路由 / 工具选择 / 引用准确率 / 多 Agent 指标 | 2 天 | WT-G2 |
| 主控集成 | 合并 4 WT + E2E + 文档 | 2 天 | 全部 |

**总估时**：11-13 天，4 WT 并行 + 集成

---

## 二、我的建议：阶段 5（Web Chat）

**理由**：

1. **已有 Wave 1 基础**：D 包搭了 FastAPI + WebSocket + 6 路由骨架 + `RuntimeAdapter`，不是从零开始
2. **业务 Agent 链路补全**：Wave 2 真实链路（Router + Synthesizer + 6 业务 Tool + 事件 handler）已经能通过 WebSocket 透传到 Web 端
3. **可视化价值最高**：用户能在浏览器看到 RAG 引用 / ECharts 图表 / Synthesizer 汇总，比 TUI 体验更好
4. **与 v1 §7.2 demo 定位一致**：前端 mock 渲染，不依赖真实外部服务
5. **可多 WT 并行**：3 个 WT 文件域基本不重叠（events / ui / tool bridge），冲突风险低

**Vector Memory 风险**：外部依赖（ES / pgvector）+ API key 管理，与 demo 定位有冲突；Embedding 真实化需 LLM API
**Eval Dashboard 工作量最大**：4 个 WT + 11-13 天，前端占 3-4 天；如果先做 Web，Eval 可以推到 Wave 4

---

## 三、不论选哪个，都需要先做：TUI 实际改动（B6）

TUI 改动是 Wave 2 收尾遗留，与 Wave 3 独立，但**优先级最高**（用户 2026-07-22 明确要求）。

TUI 改动拆 3 个 WT（**已启动**）：

| WT | 范围 | 状态 |
|---|---|---|
| WT-D1 Route Panel | `tui/route_panel.py` + 单元测试 | ⏸ 跑中 |
| WT-D2 Event Widget | `tui/business_event_widget.py` + 单元测试 | ⏸ 跑中 |
| WT-D3 Output Widgets | `tui/citation_widget.py` + `chart_metadata_widget.py` + `synthesizer_view.py` + 单元测试 | ⏸ 跑中 |
| 主控集成 | 在 `tui/app.py` 挂载 4 个 widget（RoutePanel / BusinessEventWidget / CitationWidget / ChartMetadataWidget / SynthesizerView） | 待启动 |

预计 30-60 分钟完成 TUI 改动 + 集成。

---

## 四、Wave 3 实施流程（不论选哪个阶段）

按 Wave 1 + Wave 2 成熟模式：

1. **用户选方向**（从 1.1 / 1.2 / 1.3 三选一，或选多个并行）
2. **主 agent 写详细 plan**（在本文档基础上展开 200-300 行详细计划）
3. **创建 N 个 worktree**（按阶段 5 拆 3 个 / 阶段 6 拆 3 个 / 阶段 7 拆 4 个）
4. **启动 N 个 sub-agent 并行**（每个 2-3 天工作量）
5. **主 agent 集成**：建 `integration/aigroup-wave3` 分支，merge N 个 WT，零冲突自动合 main
6. **全量验证** + 文档收尾 + push origin

---

## 五、Wave 3 关闭判定（通用）

- [ ] 用户选定方向（1.1 / 1.2 / 1.3 / 多选）
- [ ] Wave 3 详细计划书合并
- [ ] N 个 WT 全部合入 `integration/aigroup-wave3` → `main`
- [ ] 自动化测试 +N passed（具体数字看阶段）
- [ ] mypy 0 issue
- [ ] ruff 0 新增
- [ ] 文档同步：`docs/迁移记录/最小闭环验收记录.md` 新增 Wave 3 章节
- [ ] （如涉及前端）`apps/web-chat/` 或 `apps/dashboard/` 脚手架 + 基础页面

---

## 六、参考

- 方案：`kivi-agent与aigroup整合实施方案.md` §5 阶段 5-7 / §8.5 Wave 3
- v1 契约：`docs/contracts/v1.md`（不变）
- Wave 2 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 2" 章节
- Wave 1 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 1" 章节
- TUI 演示计划：`docs/迁移记录/wave2-tui-demo-plan.md`

---

**Wave 3 起草**：Mavis（主控 Agent）
**当前状态**：**待用户选方向**（1.1 / 1.2 / 1.3 / 多选）
**下一步**：TUI 改动收尾（已启动 3 个 sub-agent）→ 用户午休回来选 Wave 3 方向
