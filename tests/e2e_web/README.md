# WT-E5 E2E 测试（agent: package-web-e2e-v3）

> Wave 3 端到端测试套件 — 验证 kivi-agent Web Chat 全链路（Gateway + 业务事件 + WS + 浏览器）

## 概述

4 个 Playwright E2E 场景 + 1 个 FakeAgentRuntime 单元测试套件，验证 Wave 3 关键路径：

| 测试文件 | 覆盖场景 | 截图 |
|---|---|---|
| `tests/session_lifecycle.spec.ts` | 用户创建 session + 多意图 query → RoutePanel + Citation + Chart 全链路 | `screenshots/session_lifecycle.png` |
| `tests/cancel.spec.ts` | goal 含"取消" → 触发 RunCancelled 事件流 | `screenshots/cancel.png` |
| `tests/reconnect.spec.ts` | 浏览器断网 + 恢复 → UI reconnecting → 重连 | `screenshots/reconnect.png` |
| `tests/multi_intent.spec.ts` | 多意图 query → rag + web_search + synthesizer 链 | `screenshots/multi_intent.png` |

## 架构

```
┌─────────────────┐  HTTP/POST  ┌──────────────────┐
│  test_page.html │ ──────────► │ FastAPI Gateway  │
│   (5173)        │             │   (8000)         │
│                 │ ◄────────── │                  │
│  ┌──────────┐   │   WebSocket │  ┌────────────┐  │
│  │ data-    │   │   events    │  │ FakeAgent  │  │
│  │ testid   │   │             │  │ Runtime    │  │
│  │ contract │   │             │  │ (injected) │  │
│  └──────────┘   │             │  └────────────┘  │
└─────────────────┘             └──────────────────┘
```

**关键约束**：

- `tests/e2e_web/` 是**独立**子目录，有自己的 `package.json` + `playwright.config.ts`
- Playwright webServer 同时启动 2 个进程：test page server（5173）+ FastAPI Gateway（8000）
- FastAPI Gateway 注入 `FakeAgentRuntime`（in-process Python mock），**真实事件流** 经过 WebSocketBridge 推到浏览器
- 浏览器侧没有 mock：使用 vanilla JS 测试页（`fixtures/test_page.html`）镜像 Vue 组件的 `data-testid` 契约

## 与 apps/web-chat/ 的契约

`fixtures/test_page.html` 是**最小测试页**，**不**是产品前端。它的作用是：

1. 在 `apps/web-chat/`（WT-E2 范围）合并前提供满足 `data-testid` 契约的 DOM
2. 验证 Gateway 端到端：HTTP + WebSocket + 业务事件流

**契约清单**（`data-testid` 必须存在）：

| 元素 | testid | 用途 |
|---|---|---|
| 新建会话按钮 | `new-session-button` | 侧边栏 |
| 目标输入框 | `session-goal-input` | placeholder="输入目标..." |
| 发送按钮 | `send-button` | 触发 session 创建 |
| 停止按钮 | `cancel-button` | 取消运行 |
| 连接状态 | `connection-status` | data-state="connected\|reconnecting\|closed" |
| 重连提示 | `reconnecting-status` | 断线时显示 |
| 路由面板 | `route-panel` | 含 `.profile-tag` / `.badge` |
| 引用 widget | `citation-widget` | 含 `<li>` 列表 |
| 图表 widget | `chart-widget` | 含 `.bar` |
| 取消横幅 | `cancelled-banner` | RunCancelled 事件渲染 |

**WT-E2 合并后**：把 `playwright.config.ts` 的 `webServer[0].command` 改为 `cd ../../apps/web-chat && npm run dev` 即可。Vue 组件使用相同 testid 时无需修改测试。

## 已知调整

1. **测试页是 vanilla JS stub 而非 Vue 3**（apps/web-chat/ 尚未合并到 main）
2. **WebSocketBridge 包了 `_PumpingBridge`**：现有 `WebSocketBridge` 本身不订阅 runtime 事件流
   （`subscribe_events` 由 `RuntimeAdapter` 持有，但 Bridge 没接 Adapter）；本 E2E 在
   `connect()` 期间启动一个 task 订阅 `FakeAgentRuntime` 并转发给 inner bridge。
   WT-E1 真实链路下由事件桥接代码负责。
3. **CORS middleware**：测试页（5173）跨域调 Gateway（8000）；E2E runner 临时加
   `CORSMiddleware`。生产由 Vite proxy 同源转发，不需要。
4. **chromium 启动参数加 `--no-proxy-server`**：避免系统代理拦截 127.0.0.1。
5. **fake runtime 同步事件流**：事件 0 间隔触发；不存在"mid-run 取消"窗口，
   所以 cancel.spec.ts 只测 cancel 模式事件流契约，不测"用户中途按停止按钮"。
6. **session_lifecycle 和 multi_intent 截图视觉相似**：两者都用 multi_intent 关键词触发
   rag + chart 事件。差异化通过不同的 user 消息气泡（`对比网上 RAG 资料和我们内部知识库`
   vs `对比网上关于 RAG 的最新文章和我们内部知识库`）。

## 已知遗留

- **WT-E2 合并后需重写 `fixtures/test_page.html`**：删掉 stub 改用 Vue 真前端；
  `gateway_runner.py` 的 CORS / _PumpingBridge 也需评估是否仍必要
- **真实 kivi-core 接入后**：`_PumpingBridge` 改为 `RuntimeAdapter._on_socket_event` →
  `WebSocketBridge.publish()` 链路（WT-E1 范围）
- **取消按钮 UI 测试** 缺失：fake runtime 同步触发，无法制造 mid-run 窗口；
  真实链路下需要 LLM streaming + tick_interval 配置
- **TS 类型** 用 `// @ts-check` 隐式（Playwright 自带）但未单独跑 `tsc --noEmit`

## 复现步骤

```bash
cd /Users/kivi/Documents/agent系统/Kama/kivi-agent-wt-wave3-e2e/tests/e2e_web

# 1. 安装 Playwright + 浏览器（首次）
npm install
npx playwright install --with-deps chromium

# 2. 安装 Python 依赖（项目根）
cd ../../
uv sync --group dev
cd tests/e2e_web

# 3. 跑 fake_runtime 单元测试
unset http_proxy https_proxy all_proxy NO_PROXY no_proxy
.venv_check=1 ../../.venv/bin/python -m pytest fixtures/test_fake_runtime.py -v

# 4. 跑 E2E（自动启 Gateway + test page server）
unset http_proxy https_proxy all_proxy NO_PROXY no_proxy
npx playwright test

# 5. 单独跑某个测试
npx playwright test session_lifecycle
npx playwright test cancel
npx playwright test reconnect
npx playwright test multi_intent

# 6. 截图位置
ls screenshots/
# → cancel.png  multi_intent.png  reconnect.png  session_lifecycle.png
```

## 文件清单

```
tests/e2e_web/
├── README.md                          # 本文件
├── package.json                       # Playwright 依赖
├── playwright.config.ts               # webServer + viewport + chromium 启动参数
├── fixtures/
│   ├── fake_runtime.py                # Mock kivi-core AgentRuntime（in-process）
│   ├── test_fake_runtime.py           # 4 个单测（multi_intent / cancel / fallback / multi-subscriber）
│   ├── gateway_runner.py              # FastAPI + FakeAgentRuntime + _PumpingBridge
│   ├── test_page_server.py            # 静态文件服务器（5173）
│   └── test_page.html                 # vanilla JS 测试页（data-testid 契约）
├── tests/
│   ├── session_lifecycle.spec.ts      # E2E 1
│   ├── cancel.spec.ts                 # E2E 2
│   ├── reconnect.spec.ts              # E2E 3
│   └── multi_intent.spec.ts           # E2E 4
├── screenshots/
│   ├── session_lifecycle.png          # 1280x836
│   ├── cancel.png                     # 1280x720
│   ├── reconnect.png                  # 1280x1458
│   └── multi_intent.png               # 1280x836
└── test-results/                      # Playwright 输出（失败 trace）
```
