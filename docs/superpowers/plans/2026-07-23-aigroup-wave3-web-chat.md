# aigroup Wave 3：Web Chat（Vue 3 + FastAPI Gateway 真实联调）

> **基线**：`main @ 7d4709f`（aigroup Wave 2 完整收官含 TUI 改动，931 passed / 175 files / ruff 45）
> **日期**：2026-07-23
> **承接关系**：方案 §5 阶段 5（Web Gateway、Chatbox 与前端工具）实施；用户 2026-07-23 选定 Web Chat 为 Wave 3 主方向
> **不做**：登录 / 租户 / 企业权限 / 真实 RAG / DB / Vector Memory / 完整 Eval Dashboard / SynthesizerView

---

## 一、目标

把 Wave 1 Gateway 骨架 + Wave 2 业务 Agent 真实链路 + Wave 2 收尾 TUI 改动**升级为 Web Chat 产品入口**：

- 用户在浏览器**创建会话 / 发送任务 / 看流式响应**
- Web 端展示**路由决策 / 业务事件 / 引用 / 图表**
- Web 端支持**取消任务 / 重连 / 错误恢复**
- **Mock Tool 端到端演示**：复用 Wave 1 6 业务 Tool Mock，跑通"对比网上关于 RAG 的最新文章和我们内部知识库"多意图 query

---

## 二、范围

### 2.1 必做（Wave 3 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| E1 | Gateway & WebSocket 真实联调（事件透传 + Heartbeat） | 2-3 天 | `src/kivi_agent/gateway/` 扩展 + 单元/集成测试 |
| E2 | Vue 3 Chat 页面 + 会话状态 | 3-4 天 | `apps/web-chat/` Vite + Vue 3 + Pinia + TypeScript |
| E3 | Web 端事件组件（RoutePanel / CitationWidget / ChartWidget） | 2-3 天 | `apps/web-chat/src/components/` + Storybook 可选 |
| E4 | 取消 / 重连 / 错误状态 | 1-2 天 | `apps/web-chat/src/composables/` + WebSocket 状态机 |
| E5 | E2E + 回归测试 | 2 天 | `tests/e2e_web/`（Playwright 或 vitest + jsdom） |
| 主控 | 5 WT 集成 + 文档 + 演示截图 | 2-3 天 | `integration/aigroup-wave3` 分支 → main |

**总估时**：12-17 天，5 WT 并行 + 集成

### 2.2 明确不做（推迟到 Wave 4+）

| 项 | 推迟理由 | 后续 |
|---|---|---|
| 登录 / 租户 / 企业权限 | 个人版不需要 | Wave 4 |
| 真实 RAG / DB / 外部服务接入 | v1 §7.2 demo 定位 | Wave 4+ |
| Vector Memory Backend | 方案 §5 阶段 6 | Wave 4 |
| 完整 Evaluation Dashboard | 方案 §5 阶段 7 | Wave 4+ |
| SynthesizerView Web 端 | 需先实现 `synthesizer.completed` 事件（Wave 2 收尾已知遗留） | Wave 4 |

---

## 三、5 个 WT 拆分（按用户建议）

### WT-E1 Gateway & WebSocket 实际联调

**目标**：把 Wave 1 6 路由 stub 升级为真实联调 + 业务事件通过 WS 透传。

**任务**：
- 业务事件透传：6 类 v1 事件（LlmThinkingEvent / ChartRenderedEvent / RagSourcesCitedEvent / FrontendToolCallRequested / Responded / RunCancelledEvent）从 `core.bus` 通过 `WS Bridge` 推到前端
- Heartbeat：每 15s 发一个 `{type: "ping", ts: ...}` 事件，前端 30s 没收到就断线提示
- 重连协议：前端断线重连时，gateway 缓存最近 100 条事件，重连时 replay（`?since=<ts>` query）
- 取消协议增强：`POST /sessions/{id}/cancel` 返回后，gateway 立刻推 `RunCancelledEvent` 给所有 WS 客户端
- 错误码标准化：FastAPI 错误响应统一 `{code, message, hint, ts}` 格式

**交付文件**：
- `src/kivi_agent/gateway/main.py`（扩展现有 318 行）
- `src/kivi_agent/gateway/event_bridge.py`（新，业务事件路由）
- `src/kivi_agent/gateway/heartbeat.py`（新）
- `src/kivi_agent/gateway/replay.py`（新）
- `tests/unit/test_gateway_event_bridge.py`（新）
- `tests/unit/test_gateway_heartbeat.py`（新）
- `tests/unit/test_gateway_replay.py`（新）

### WT-E2 Vue Chat 页面 + 会话状态

**目标**：从零搭建 Vue 3 Chat 前端，含会话管理 UI。

**任务**：
- 初始化 Vite + Vue 3 + TypeScript + Pinia + vue-router 项目（`apps/web-chat/`）
- 路由：`/` 会话列表 + `/chat/:sessionId` 聊天页
- 组件：`SessionList` / `ChatView` / `MessageList` / `MessageInput` / `SessionHeader`
- 状态管理：Pinia store 持有 `sessions` / `currentSession` / `messages` / `wsConnectionState`
- API 客户端：`fetch` 封装 + `WebSocket` 封装（断线重连 / 心跳 / 错误处理）
- 基础样式：Tailwind CSS 或 Naive UI（暂用 Tailwind）
- Vite dev server proxy 到 FastAPI Gateway

**交付文件**（全部在 `apps/web-chat/`）：
- `package.json` / `vite.config.ts` / `tsconfig.json` / `tailwind.config.js`
- `src/main.ts` / `src/App.vue` / `src/router.ts`
- `src/stores/session.ts` / `src/stores/message.ts` / `src/stores/ws.ts`
- `src/views/SessionList.vue` / `src/views/ChatView.vue`
- `src/components/SessionList.vue` / `src/components/MessageList.vue` / `src/components/MessageInput.vue` / `src/components/SessionHeader.vue`
- `src/api/session.ts` / `src/api/ws.ts`
- `src/types/api.ts`（TypeScript 类型，与后端 Pydantic 对齐）
- `src/style.css` / `index.html`

### WT-E3 路由 / 引用 / 图表 Web 端事件组件

**目标**：在 Web 端展示 3 类业务事件（RouteDecision / RagSourcesCited / ChartRendered），对应 TUI 的 RoutePanel / CitationWidget / ChartMetadataWidget。

**任务**：
- `RoutePanel.vue`：路由决策展示（intent + confidence + target_profiles 链路 + matched keywords），cyan 卡片
- `CitationWidget.vue`：RAG 引用列表，每条来源可点击展开
- `ChartWidget.vue`：ECharts 元数据 mock 渲染（用 ECharts for Vue 真实画图，不只是 metadata 展示）
- 3 个组件订阅 `ws.ts` 的事件流，按 `event.type` 路由
- 复用 Wave 2 业务事件 handler 的设计思路

**交付文件**（全部在 `apps/web-chat/src/components/`）：
- `RoutePanel.vue` / `RoutePanel.spec.ts`
- `CitationWidget.vue` / `CitationWidget.spec.ts`
- `ChartWidget.vue` / `ChartWidget.spec.ts`
- `src/composables/useBusinessEvents.ts`（事件流 composable）

### WT-E4 取消 / 重连 / 错误状态

**目标**：WebSocket 状态机 + 用户交互 + 错误恢复。

**任务**：
- WS 状态机：`connecting` / `open` / `reconnecting` / `closed` / `error` 5 个状态
- 心跳：每 10s 发 ping，30s 没收到 pong 就 reconnect
- 重连：指数退避（1s / 2s / 4s / 8s / 16s / 30s max）
- 取消按钮：用户在 ChatView 顶部"停止"按钮 → `POST /sessions/{id}/cancel` + 本地立即隐藏输入
- 错误展示：API 错误 / WS 错误 / 业务错误三档，顶部 banner + 行内提示
- EventSource（备选）：如 WebSocket 不行，fallback 到 SSE

**交付文件**（全部在 `apps/web-chat/src/`）：
- `composables/useWebSocket.ts`（状态机 + 心跳 + 重连）
- `composables/useCancel.ts`（取消协议）
- `composables/useErrorHandler.ts`（错误状态机）
- `components/ConnectionStatus.vue`（状态指示器）
- `components/ErrorBanner.vue`（错误 banner）
- `components/CancelButton.vue`（停止按钮）

### WT-E5 E2E + 回归测试

**目标**：端到端测试覆盖 Wave 3 关键路径。

**任务**：
- Playwright E2E（推荐）：
  - 启动 Vite dev server + FastAPI Gateway + mock kivi-core（in-process fake AgentRuntime）
  - 测试 1：用户登录 → 创建 session → 发送 query → 看到 RoutePanel + 引用 + 汇总
  - 测试 2：用户取消 → 看到 RunCancelledEvent + 输入禁用
  - 测试 3：WS 断线 → 自动重连 → 事件 replay
  - 测试 4：多意图 query → 看到多个 Profile 并行 + Synthesizer 汇总
- 回归：现有 931 单测全过 + 新增 E2E 全过
- 截图：4 个 E2E 场景的成功截图，作为 Wave 3 收官视觉证据

**交付文件**（全部在 `tests/e2e_web/`）：
- `playwright.config.ts` / `package.json`
- `fixtures/fake_runtime.py`（mock kivi-core）
- `tests/session_lifecycle.spec.ts` / `tests/cancel.spec.ts` / `tests/reconnect.spec.ts` / `tests/multi_intent.spec.ts`
- `screenshots/`（4 张 E2E 成功截图）

---

## 四、目录结构

### 新增

```
src/kivi_agent/gateway/
  event_bridge.py           # WT-E1 业务事件路由
  heartbeat.py              # WT-E1 心跳
  replay.py                 # WT-E1 事件 replay

apps/web-chat/              # WT-E2/E3/E4 全部新增
  package.json
  vite.config.ts
  tsconfig.json
  tailwind.config.js
  index.html
  src/
    main.ts
    App.vue
    router.ts
    style.css
    api/
      session.ts
      ws.ts
    composables/
      useWebSocket.ts
      useCancel.ts
      useErrorHandler.ts
      useBusinessEvents.ts
    stores/
      session.ts
      message.ts
      ws.ts
    views/
      SessionList.vue
      ChatView.vue
    components/
      SessionList.vue
      MessageList.vue
      MessageInput.vue
      SessionHeader.vue
      ConnectionStatus.vue
      ErrorBanner.vue
      CancelButton.vue
      RoutePanel.vue
      CitationWidget.vue
      ChartWidget.vue
    types/
      api.ts

tests/e2e_web/              # WT-E5 全部新增
  package.json
  playwright.config.ts
  fixtures/
    fake_runtime.py
  tests/
    session_lifecycle.spec.ts
    cancel.spec.ts
    reconnect.spec.ts
    multi_intent.spec.ts
  screenshots/
```

### 修改

```
src/kivi_agent/gateway/main.py        # WT-E1 扩展（事件透传 + heartbeat + replay + 错误码）
src/kivi_agent/gateway/deps.py        # WT-E1 扩展（注入 event_bridge / heartbeat / replay）
pyproject.toml                        # 加 [gateway] extras + web-chat 入口脚本（可选）
docs/contracts/v1.md                  # 不修改（v1 冻结）；新增 v1 附录说明 Web 端 type 对齐
docs/迁移记录/最小闭环验收记录.md      # 新增 Wave 3 章节
```

---

## 五、Wave 3 实施流程

按 Wave 1 / Wave 2 成熟模式：

1. **5 个 worktree 并行**（`integration/aigroup-wave3-{gateway,vue,components,ws-state,e2e}`）
2. **5 个 sub-agent 并行**（每个 2-4 天工作量，按 Wave 2 经验实际 30-60 分钟就跑完代码部分）
3. **主控集成**：
   - 建 `integration/aigroup-wave3` 分支（基于 main `7d4709f`）
   - 顺序 merge 5 个 WT
   - 处理冲突（如有）
   - 跑全量测试
   - 修 ruff
   - 写文档
   - 推 origin
4. **关闭判定**（见 §七）

---

## 六、风险与缓解

| 风险 | 缓解 |
|---|---|
| 前端从零开始，工作量比后端大 | 严格锁定 5 个 WT 范围；不扩大到 Naive UI / 国际化 / 主题切换 |
| 5 个 WT 并行可能撞车 | WT-E1 后端 / WT-E2/E3/E4 前端 文件域 100% 分离；E5 写测试不写主代码 |
| Vue 3 + TypeScript 子 agent 不熟 | sub-agent 先读 Wave 1 Gateway 代码理解 IPC 协议；用成熟栈（Vite + Tailwind） |
| Gateway 扩展 6 路由事件透传可能漏事件 | E5 E2E 覆盖每类事件类型 |
| WebSocket 重连 + Replay 协议复杂 | 先简化：replay 100 条最近事件（够用） |

---

## 七、Wave 3 关闭判定

- [ ] 5 个子包全部合入 `integration/aigroup-wave3` → `main`
- [ ] 5 个 merge 零冲突自动合
- [ ] 自动化测试 931+ passed / 0 failed（新增数待统计）
- [ ] mypy 0 issue（后端）
- [ ] TypeScript compile 0 error（前端）
- [ ] ruff 0 新增（后端）
- [ ] eslint 0 error（前端）
- [ ] Gateway 6 路由真实联调（不是 stub）
- [ ] WS 业务事件透传（6 类 v1 事件 + SessionCancel）
- [ ] WS Heartbeat + 重连 + Replay
- [ ] Vue Chat 页面端到端：创建 / 发送 / 看到 RoutePanel + 引用 + 图表 / 取消 / 重连
- [ ] E2E 4 场景 + 截图
- [ ] 文档同步：最小闭环验收记录新增 Wave 3 章节
- [ ] 演示录屏 / 截图（4 个 E2E 成功截图）

---

## 八、Wave 4+ 候选

按方案 §8.5 后续 wave：

| Wave | 内容 | 估时 |
|---|---|---|
| Wave 4 | 真实 RAG / DB 接入（替换 Mock）+ Eval T11/T12 | 50+ 天 |
| Wave 5 | Vector Memory Backend | 20+ 天 |
| Wave 6 | 完整 Evaluation Dashboard | 30+ 天 |
| Wave 7 | Web Chat 深化（登录 / 租户 / 多用户） | 30+ 天 |

---

## 九、参考

- 方案：`kivi-agent与aigroup整合实施方案.md` §5 阶段 5
- v1 契约：`docs/contracts/v1.md`（不变；Web 端用 Pydantic 模型反推 TypeScript 类型）
- Wave 2 收尾 TUI：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 2 收尾 TUI 改动" 章节
- Wave 2 收官：`docs/迁移记录/最小闭环验收记录.md` "aigroup Wave 2" 章节
- Gateway 现状：`src/kivi_agent/gateway/main.py`（318 行 6 路由 stub）
- TUI 演示计划：`docs/迁移记录/wave2-tui-demo-plan.md`（Web 端结构类似）
- 业务事件：`src/kivi_agent/core/bus/handlers/business.py`（v1 §5.2.1 6 事件聚合）

---

**Wave 3 起草**：Mavis（主控 Agent）
**用户批准**：2026-07-23 "选 Web Chat，直接开 Wave 3"
**下一步**：创建 5 个 worktree + 启动 5 个 sub-agent（WT-E1/E2/E3/E4/E5 并行）
