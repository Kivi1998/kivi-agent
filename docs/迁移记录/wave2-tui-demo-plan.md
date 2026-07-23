# aigroup Wave 2 — TUI 演示计划

> **基线**：`integration/aigroup-wave2-events`（WT 在写本文档时尚未合入 B5/B6）
> **对应任务**：Wave 2 计划 §五 / 任务 B6（演示路径文档部分）
> **范围**：本文档是 B6 在当前 WT 的交付物（仅计划 + 复现步骤），不包含 `tui/app.py` 的代码改动

---

## 一、目标

让用户在 TUI 真实跑一个**多意图业务 query**，端到端看到 4 类信息：

1. **路由决策日志**：BusinessRouter 把 query 分流到哪些 Profile
2. **RAG 引用**：RagSourcesCitedEvent 触发的引用 + 标题
3. **图表元数据**：ChartRenderedEvent 的 ECharts option dict（mock 展示）
4. **Synthesizer 汇总**：多个 SubResult 合并后的最终答案

**演示 query**（沿用 Wave 2 plan §5 E2E 示例）：

> 对比网上关于 RAG 的最新文章和我们内部知识库

---

## 二、范围

### 2.1 在当前 WT 范围（本文档）

| 任务 | 状态 | 说明 |
|---|---|---|
| 业务事件 handler（BusinessEventHandler） | ✅ 已完成（commit `9a70f5e`） | 订阅 6 类业务事件按 run_id 聚合 |
| 业务事件 E2E 测试 | ✅ 已完成（commit `73af57b`） | 4 场景端到端事件流断言 |
| **TUI 演示计划文档** | ✅ **本文档** | 用户复现步骤 + 预期截图描述 |

### 2.2 不在当前 WT 范围（推迟）

| 项 | 推迟原因 | 后续 |
|---|---|---|
| `tui/app.py` 业务事件渲染面板 | B6 改 TUI 涉及大改，与主控集成期绑定 | 主控集成期统一改 |
| 真实业务 Profile 接入到 TUI 主循环 | 依赖 WT-A 5 个 Profile TOML + WT-B Router/SynthesizerRunner 合并 | 主控集成期 |
| ECharts 真实渲染 | D 阶段 Web 端职责，TUI 仅 mock 展示 metadata | D 阶段 |

### 2.3 为什么把 TUI 改留到主控

- `tui/app.py` 当前 1300+ 行，文本面板/事件订阅/键盘交互深度耦合
- 业务 Profile 接入需要协调 5 个 Profile TOML 的加载顺序与并发执行
- Router/SynthesizerRunner 还在 WT-B 并行 worktree，未稳定
- 主控集成期做 TUI 改：a) 一次合并避免反复 cherry-pick；b) 能拿到 WT-A + WT-B 的最终接口

---

## 三、用户复现步骤

### 3.1 启动命令

```bash
# 1. 启动 daemon
cd /Users/kivi/Documents/agent系统/Kama/kivi-agent
KAMA_PORT=7437 uv run kivi-core

# 2. 另开终端，启动 TUI
cd /Users/kivi/Documents/agent系统/Kama/kivi-agent
uv run kivi-tui
```

### 3.2 TUI 操作序列

1. **新建 session**：按 `Ctrl+N` 创建新会话，模式选 `chat`
2. **输入演示 query**：在 prompt 区输入
   ```
   对比网上关于 RAG 的最新文章和我们内部知识库
   ```
   按 `Enter` 提交
3. **观察路由决策日志**（30 秒内）：
   - TUI 事件流面板（"Steps / Events"）应出现 `llm.thinking` 事件，content 包含 `routing: multi-intent → ['web_search', 'rag', 'synthesizer']`
4. **观察 RAG 引用**（1 分钟内）：
   - 出现 `rag.sources_cited` 事件，sources 列表含 2 条：
     - `{id: "kb-001", title: "RAG 系统架构综述", score: 0.95}`
     - `{id: "kb-002", title: "企业内部知识库最佳实践", score: 0.92}`
5. **观察 ECharts 元数据**（如果 query 触发 database Profile）：
   - 出现 `chart.rendered` 事件，option_dict 包含 `xAxis` / `series` 字段
   - TUI mock 渲染：用 ASCII box 展示 `chart_type: bar` / 标题 / X 轴标签
6. **观察 Synthesizer 汇总**（2 分钟内）：
   - 出现第 2 条 `llm.thinking`，content 包含 `synthesizing 2 sub-results`
   - 最终输出面板出现合并后的答案（包含 RAG 引用编号 + Web 搜索结果段落）

### 3.3 中断测试（可选）

```bash
# 另开终端，触发 SessionCancel
KAMA_PORT=7437 uv run kivi session cancel --session-id <session_id>
```

预期：
- TUI 出现 `run.cancelled` 事件（reason="user_requested"）
- 子 Profile（rag / web_search）的 step 在 1s 内停止
- 最终输出面板显示「已取消」

---

## 四、预期截图描述

### 4.1 路由决策阶段（TUI 顶部 Steps 面板）

```
┌─ Steps ─────────────────────────────────────────────┐
│ [12:00:01] Step 0  routing  → [web_search, rag,    │
│                              synthesizer]            │
│ [12:00:02] llm.thinking  parent-run-1               │
│             "对比网上关于 RAG 的最新文章..."         │
└──────────────────────────────────────────────────────┘
```

### 4.2 子 Agent 触发阶段（中间 Events 流）

```
┌─ Events ────────────────────────────────────────────┐
│ [12:00:03] tool.call_started  rag_query             │
│             params={"query": "RAG 最新文章"}        │
│ [12:00:04] rag.sources_cited  sub-rag-1             │
│             2 sources: [kb-001, kb-002]             │
│ [12:00:05] tool.call_started  web_search            │
│ [12:00:06] llm.thinking  sub-web-1                  │
└──────────────────────────────────────────────────────┘
```

### 4.3 图表元数据阶段（如果 database Profile 触发）

```
┌─ Chart (Mock) ──────────────────────────────────────┐
│ Type: bar                                           │
│ Title: Bar Chart (Mock)                             │
│ X axis: [Q1, Q2, Q3]                                │
│ Series [count]: [10, 20, 30]                        │
│ ────────────────────────────────────                │
│ [bar chart ASCII rendering]                         │
│   30 ┤           ███                                │
│   20 ┤     ███  ███                                  │
│   10 ┤ ███ ███  ███                                  │
│      └─Q1──Q2──Q3─                                   │
└──────────────────────────────────────────────────────┘
```

### 4.4 Synthesizer 汇总阶段（底部 Output 面板）

```
┌─ Output ────────────────────────────────────────────┐
│ 综合对比网上文章与内部知识库，关于 RAG 的要点：      │
│                                                       │
│ ## 网上最新文章                                      │
│ 2025-2026 年 RAG 架构演进集中在...                   │
│                                                       │
│ ## 内部知识库（kb-001, kb-002）                       │
│ - RAG 系统架构综述 [1]                                │
│ - 企业内部知识库最佳实践 [2]                          │
│                                                       │
│ 综合建议：优先采用 hybrid retrieval + bge-reranker    │
│ 参考：[1] kb-001  [2] kb-002                          │
└──────────────────────────────────────────────────────┘
```

### 4.5 SessionCancel 后状态

```
┌─ Steps ─────────────────────────────────────────────┐
│ [12:01:30] run.cancelled  parent-run-1              │
│             reason: "user_requested"                │
│ [12:01:30] subagent.finished  sub-rag-1  failed     │
│ [12:01:30] subagent.finished  sub-web-1 failed      │
└──────────────────────────────────────────────────────┘

┌─ Output ────────────────────────────────────────────┐
│ ⚠️ 会话已取消                                        │
│ 原因：user_requested                                 │
└──────────────────────────────────────────────────────┘
```

---

## 五、技术实现要点（给主控集成期的备忘）

### 5.1 事件订阅位置

TUI 在 `tui/app.py` 启动时创建 `EventBus.subscribe()` 监听：

- `llm.thinking` → 更新 Steps 面板
- `rag.sources_cited` → 追加引用到 Output 面板
- `chart.rendered` → 触发 chart mock 渲染面板
- `run.cancelled` → 显示取消状态

### 5.2 多意图路由可视化

TUI 需要调用 Router 接口（WT-B 的 `BusinessRouter.route(query)`）才能展示路由决策日志。这要求：

1. Router 在 SessionCreate 时暴露（避免每条 query 重新路由）
2. Router 输出 RouteDecision 含 `target_profiles: list[str]`
3. TUI 在收到 `llm.thinking` 时检查 content 是否含 `routing: ...` 关键词

### 5.3 ECharts 真实渲染

TUI mock 仅展示 `option_dict` 字段（标题 / X 轴 / series），不引入 ECharts JS（D 阶段 Web 职责）。集成时用 `textual.widgets.Static` 渲染简单表格或 ASCII 柱状图。

### 5.4 SessionCancel 入口

TUI 顶栏加 `Ctrl+X` 快捷键 → 触发 `session.cancel` 命令（v1 §5.2.2）。命令通过 IPC 发到 daemon，daemon 推 `run.cancelled` 事件回 TUI。

---

## 六、验收判定

| 验收点 | 状态 |
|---|---|
| 用户能复现 §3 操作序列 | 主控集成期验证 |
| 路由决策日志可见 | 主控集成期验证 |
| RAG 引用 + ECharts metadata + Synthesizer 输出三件套可见 | 主控集成期验证 |
| SessionCancel 中断子 run | 主控集成期验证 |
| 业务事件 handler 单元 / E2E 测试通过 | ✅ 已完成（commit `9a70f5e` + `73af57b`） |

---

## 七、参考

- Wave 2 计划：`docs/superpowers/plans/2026-07-22-aigroup-wave2-business-agent.md` §五（B6 演示）
- v1 契约：`docs/contracts/v1.md` §5.2.1（6 事件）+ §5.2.2（SessionCancel）
- BusinessEventHandler 单元测试：`tests/unit/test_business_event_handler.py`
- 业务 E2E 测试：`tests/e2e/test_business_agent_e2e.py`
- TUI 入口：`src/kivi_agent/tui/app.py`（主控集成期改）

---

**记录人**：Mavis（自动化 agent）
**关联 commit**：
- `9a70f5e` — BusinessEventHandler + 单元测试
- `73af57b` — 业务 E2E 测试
- 本文档 commit — TUI 演示计划

**下一步**：本文档是 B6 范围的最后一块（仅文档）。TUI 代码改动（`tui/app.py`）推迟到主控集成期，由主控 Agent 统一协调 WT-A / WT-B / 本 WT 三个 worktree 合并后实施。
