# aigroup Wave 2：业务 Agent 真实链路

> **基线**：`main @ 9f063b7`（aigroup Wave 1 已收官）
> **日期**：2026-07-22
> **目标来源**：用户确认（"让业务 Agent 真正跑起来"）
> **承接关系**：方案 §8.5 的 Wave 2 实质上已由 aigroup Wave 1 完成；本文档对应方案 **Wave 3：垂直能力** 的"业务 Agent 真实链路"子集

---

## 一、目标

**让业务 Agent 真正跑起来**：

```
Root Agent
  └─ BusinessRouter（路由决策）
      ├─ 命中单意图 → 单个业务 Profile（general / rag / web_search / database）
      └─ 命中多意图 → 并行多个业务 Profile → Synthesizer Profile 汇总
```

链路接通后，调用 Wave 1 的 6 个业务 Tool（保持 Mock），Trace / 引用 / 图表事件走真实 Agent 链路。

---

## 二、范围

### 2.1 必做（Wave 2 范围）

| 序号 | 任务 | 估时 | 交付物 |
|---|---|---|---|
| B1 | 5 个业务 Profile + Prompt（`general` / `rag` / `web_search` / `database` / `synthesizer`） | 2-3 天 | `src/kivi_agent/core/agents/builtin/business/{general,rag,web_search,database,synthesizer}.toml` |
| B2 | `BusinessRouter`（意图分类 + 单/多意图路由决策） | 2-3 天 | `src/kivi_agent/core/agents/business_router.py` + `tests/unit/test_business_router.py` |
| B3 | `SynthesizerRunner`（并行多 Profile + 结果合并） | 1-2 天 | `src/kivi_agent/core/agents/synthesizer.py` + 测试 |
| B4 | 业务 Tool 接入 Profile：`rag_query` → `rag`、`web_search` → `web_search`、`query_database` → `database`、`echarts_render` → `database`（按需） | 0.5 天 | TOML `allowed_tools` 字段 |
| B5 | 事件接入：Trace `LlmThinkingEvent` / `RagSourcesCitedEvent` / `ChartRenderedEvent` 走业务 Agent 链路；E2E 测试断言事件流 | 2-3 天 | `tests/e2e/test_business_agent_e2e.py` + `core/bus/handlers/business.py` |
| B6 | TUI 演示：用户在 TUI 输入 query → 看到路由决策 + 业务 Tool 调用 + 引用 + 图表 + 汇总 | 1-2 天 | 复用 `tui/app.py` + 截图 |
| 主控 | 集成 3 worktree + 全量测试 + 文档收尾 | 2-3 天 | `integration/aigroup-wave2` 分支 → main |

**总估时**：10-15 天（3 worktree 并行压缩到 2 周左右）

### 2.2 明确不做（推迟到 Wave 3/4）

| 项 | 推迟理由 | 后续 wave |
|---|---|---|
| 6 业务 Tool 真实接入（替换 Mock） | 保持 v1 §7.2 demo 定位；外部 API Key 管理复杂 | Wave 3 |
| Web Chat / Chatbox UI | 方案 §5 阶段 5 独立阶段 | Wave 4 |
| Vector Memory Backend | 方案 §5 阶段 6；当前 LocalMemoryBackend 足够 | Wave 3 |
| Evaluation Dashboard | 方案 §5 阶段 7；Eval T11/T12 一起做 | Wave 3 |
| Eval T11/T12（24d 剩余工作） | 留 Wave 3 与 Dashboard 一起 | Wave 3 |
| 业务 Agent 多语言 / i18n | 范围外 | 不做 |
| 业务 Agent 配额 / 计费 | 个人版不涉及 | 不做 |

---

## 三、5 个业务 Profile 冻结

| Profile | allowed_tools | 用途 | system_prompt 主题 |
|---|---|---|---|
| `general` | `[]`（无业务 Tool） | 通用对话 / 简单问答 / 不需调外部工具的查询 | "你是通用助手，能用 Bash/Read/Write 等基础工具，但不能调业务 Tool" |
| `rag` | `rag_query` | 知识库问答（基于 Wave 1 实现的 RAG Tool，含引用） | "你是 RAG 助手，使用 rag_query 工具检索知识库；引用必须保留" |
| `web_search` | `web_search` | 联网搜索（基于 Wave 1 实现的 Tavily Mock） | "你是联网搜索助手，使用 web_search 工具搜索外部信息" |
| `database` | `query_database` | 问数（两阶段：SQL 生成 + 执行；ECharts 按需） | "你是数据库助手，使用 query_database 问数；如需图表会自动调 echarts_render" |
| `synthesizer` | `[]` | 多 Profile 结果汇总；只能读不能调业务 Tool | "你是合成助手，接收上游多个 Agent 的结果，去重/合并/排序/润色后输出" |

### 3.1 路由决策（冻结）

`BusinessRouter.route(query) -> list[str]` 返回按优先级排序的 Profile 名列表：

| 命中模式 | 路由结果 |
|---|---|
| 显式工具需求（如"查数据库"、"搜索"） | `[对应单 Profile]` |
| 知识库关键词（"我们公司"、"内部文档"、"FAQ"） | `[rag]` |
| 联网关键词（"网上"、"最新"、"搜一下"） | `[web_search]` |
| 数据库关键词（"表"、"字段"、"统计"、"数量"、"SUM"、"COUNT"） | `[database]` |
| 通用问题（无业务 Tool 需求） | `[general]` |
| 多意图（如"对比网上和我们知识库"） | `[web_search, rag, synthesizer]` 或 `[rag, web_search, synthesizer]` |

**优先级**（多意图时排序）：`database` > `rag` > `web_search` > `general` > `synthesizer`（synthesizer 永远在末尾兜底）

### 3.2 路由决策实现策略

**轻量级方案**（v1）：
- 关键词正则匹配 + 优先级 fallback
- 不引入 LLM-based intent classification（避免递归调用 LLM 的复杂度）
- 测试覆盖每种意图 + 混合意图

**升级路径**（v2，未来）：
- 用 LLM-based 意图分类（不阻塞 Wave 2）

---

## 四、Synthesizer 冻结

`SynthesizerRunner.run(query, sub_results)`：

```python
@dataclass
class SubResult:
    profile_name: str
    output: str           # 子 Agent 的文本输出
    citations: list[str]  # RAG 引用
    charts: list[dict]    # ECharts 元数据
    trace_ids: list[str]  # 子 run 的 trace
```

`Synthesizer` 用 `synthesizer` Profile 跑 LLM，把多个 `SubResult` 喂给 system_prompt，LLM 输出汇总文本 + 引用 + 图表元数据透传。

---

## 五、事件接入冻结

走真实 Agent 链路的事件流（按 `WIRE_PROTOCOL.md`）：

| 事件 | 触发方 | 消费方 | 业务场景 |
|---|---|---|---|
| `LlmThinkingEvent` | 各业务 Profile 推理 | 业务 Agent 链路 | 业务 Agent 决策可观察 |
| `RagSourcesCitedEvent` | `rag_query` Tool | Synthesizer + TUI 引用展示 | RAG 回答带来源 |
| `ChartRenderedEvent` | `echarts_render` Tool | TUI 图表渲染（mock 展示 metadata） | 问数结果可视化 |
| `RunCancelledEvent` | 用户/TUI 取消 | BusinessRouter 中断所有子 run | 用户中止时清理 |
| `SessionCancel` 命令 | 用户 | 业务 Agent 链路整体终止 | 同上 |

E2E 测试断言：跑一个多意图 query（如"对比网上关于 RAG 的最新文章和我们内部知识库"），断言事件流顺序为 `LlmThinkingEvent(web_search) → RagSourcesCitedEvent(rag) → ChartRenderedEvent(若有) → LlmThinkingEvent(synthesizer) → 终态 text`。

---

## 六、目录结构与文件清单

### 新增

```
src/kivi_agent/core/agents/
  business_router.py          # B2 路由决策
  synthesizer.py              # B3 Synthesizer Runner
  builtin/business/
    general.toml              # B1
    rag.toml                  # B1
    web_search.toml           # B1
    database.toml             # B1
    synthesizer.toml          # B1

src/kivi_agent/core/bus/handlers/
  business.py                 # B5 业务事件 handler

tests/unit/
  test_business_router.py             # B2
  test_synthesizer.py                 # B3
  test_business_profile_v1.py         # B1 契约硬断言（5 个 Profile 字段冻结）
  test_business_tool_profile_bind.py  # B4 业务 Tool ↔ Profile allowed_tools 对齐

tests/e2e/
  test_business_agent_e2e.py          # B5 端到端事件流断言
```

### 修改

```
src/kivi_agent/core/agents/__init__.py  # 导出 BusinessRouter
src/kivi_agent/core/runner.py          # 业务 Agent 接入主循环（如未自动）
docs/contracts/v1.md                    # （不修改，v1 契约未变）
docs/迁移记录/最小闭环验收记录.md        # 新增 Wave 2 章节
```

---

## 七、Wave 2 实施模式

**3 worktree 并行 + 1 集成分支**，沿用 Wave 1 模式：

| WT | 范围 | 依赖 | 估时 |
|---|---|---|---|
| `kivi-agent-wt-business-profiles-v2` | B1 + B4 | 无 | 2-3 天 |
| `kivi-agent-wt-router-v2` | B2 + B3 | 依赖 B1 Profile 名 | 2-3 天 |
| `kivi-agent-wt-event-bridge-v2` | B5 + B6 | 依赖 B1 B2 B3 | 2-3 天 |
| 主控（`integration/aigroup-wave2`） | 集成 + 收尾 | 全部 | 2-3 天 |

**冲突预警**：
- B1 写 5 个 TOML，B2 读 Profile 名 → 集成时检查路由表对齐
- B2 + B3 都改 `core/agents/__init__.py` → 主控合
- B5 改 `core/bus/handlers/` + `tests/e2e/` → 相对独立
- B1 + B4 同时改 `core/agents/builtin/` → 同一目录，集成时 git auto-merge

---

## 八、不修改 v1 契约

Wave 2 **不引入新 Tool 名 / 字段 / 事件**。全部沿用 v1 冻结：

- 5 Profile 名在 v1 范围内（`AgentProfile.name` 字段本就是字符串）
- 6 业务 Tool 名沿用 v1 §1
- 事件名沿用 v1 §5.2.1
- SessionCancel 沿用 v1 §5.2.2

**无需 v2 契约 / ADR**。如果未来要给 5 Profile 加 Schema（如 intent signature），走 v2 流程。

---

## 九、Wave 2 关闭判定

- [ ] 5 个业务 Profile TOML 写入 `builtin/business/`，加载测试通过
- [ ] `BusinessRouter` 覆盖 6 种路由场景（单/多意图 × 4 关键词类型 + general 兜底）
- [ ] `Synthesizer` 合并多 Profile 结果，含引用与图表元数据透传
- [ ] 业务 Tool ↔ Profile `allowed_tools` 对齐（`web_search` Profile 仅 `web_search` Tool 等）
- [ ] E2E 测试跑通多意图 query，事件流顺序断言通过
- [ ] TUI 演示：用户在 TUI 跑一个 query，看到路由 + 引用 + 图表 + 汇总
- [ ] `786+` 测试全过、mypy 0 issue、ruff 0 新增
- [ ] 文档同步：`docs/迁移记录/最小闭环验收记录.md` 新增 Wave 2 章节

---

## 十、参考

- 方案：`kivi-agent与aigroup整合实施方案.md` §8.5（Wave 3 垂直能力，本 plan 是其业务 Agent 子集）
- v1 契约：`docs/contracts/v1.md`（§1 6 Tool / §2 RunContext / §3 AgentProfile / §4 input_schema / §5 6 事件 + SessionCancel）
- Wave 1 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 1" 章节
- 内建 Profile 模板：`src/kivi_agent/core/agents/builtin/coordinator.toml`（coordinator 是 Wave 1 已有范式）

---

**Wave 2 起草**：Mavis（主控 Agent）
**批准**：用户（2026-07-22 "开 Wave 2"）
**下一步**：创建 3 个 worktree + 启动 3 个 sub-agent
