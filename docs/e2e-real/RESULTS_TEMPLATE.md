# Real LLM E2E Results Template

> **用途**：用户跑完 `tests/e2e_real/` 后，**填这个模板**，**可直接引用到简历 / 博客 / GitHub README**。
> **填写方式**：复制本文件 → 填实际数据 → 提交到 `docs/e2e-real/RESULTS.md`（重命名去掉 `_TEMPLATE`）。
> **数据来源**：`reports/e2e_real/real_llm_run_<timestamp>.json` + `.md`（`jq` 或 `cat` 提取）。

---

## 0. 填写信息（请用真实数据替换 `<...>`）

| 字段 | 填写值 |
|---|---|
| **填表人** | <你的名字 / GitHub handle> |
| **填表日期** | <YYYY-MM-DD> |
| **运行时间** | <YYYY-MM-DD HH:MM:SS> |
| **跑哪个 provider** | anthropic / openai / deepseek |
| **用哪个 model** | claude-sonnet-4-6 / gpt-4o-mini / deepseek-chat / ... |
| **跑了几个 case** | 10（5 demo + 5 eval）/ 或自定义 |
| **总耗时** | <45.23> 秒 |
| **总 token** | <12,345> |
| **总成本** | <$0.0876> USD |
| **成功率** | <100%> (10/10) |
| **平均延迟** | <3.42> 秒 |

---

## 1. 整体汇总

### 1.1 跑批数据

```bash
# 命令复现（便于读者自己跑）
export KIVI_ANTHROPIC_API_KEY=sk-ant-...   # 或 OPENAI
export KIVI_RUN_E2E=1
export KIVI_E2E_PROVIDER=anthropic
export KIVI_E2E_MAX_CASES=10
uv run pytest tests/e2e_real -q
```

### 1.2 关键指标

| 指标 | 实际值 | 期望值（参考） |
|---|---|---|
| Provider | `<anthropic>` | — |
| Model | `<claude-sonnet-4-6>` | — |
| Total Cases | `<10>` | 5 demo + 5 eval |
| Success Rate | `<100%>` (10/10) | ≥ 80% |
| Total Tokens | `<12,345>` | — |
| Total Cost (USD) | `<$0.0876>` | ≤ $0.50（5 demo + 5 eval 上限） |
| Avg Latency | `<3.42>` 秒 | ≤ 10 秒 |
| Total Duration | `<45.23>` 秒 | ≤ 5 分钟 |

### 1.3 报告文件路径

- **JSON 报告**：`reports/e2e_real/real_llm_run_<timestamp>.json`
- **Markdown 报告**：`reports/e2e_real/real_llm_run_<timestamp>.md`

<!-- screenshot: Markdown 报告渲染效果 -->

---

## 2. 5 Demo 真 LLM 期望输出

> **填法**：跑完后，对照实际 LLM 输出填到 `<实际输出>` 位置。
> **评估方式**：人工 0-5 分（0=完全错误 / 5=完美符合预期）。

### 2.1 Demo 1：编程 Agent（修 bug + 跑 pytest）

| 字段 | 期望值 | 实际值 |
|---|---|---|
| **Case ID** | `demo1_coding` | — |
| **Spec** | "修复 `demos/fixtures/demo1_coding_fixture.py` 中的 add 函数（当前是减法，应改为加法），然后跑 `python demos/fixtures/demo1_coding_fixture.py` 验证" | — |
| **期望行为** | 1. 找到 `return a - b`<br>2. 改为 `return a + b`<br>3. 跑 pytest 验证通过 | — |
| **实际输出（LLM 修复内容）** | `<实际 patch>` | — |
| **测试结果** | 3/3 通过 | `<X/3>` |
| **Output Quality Score** | 5 | `<0-5>` |
| **Input Tokens** | — | `<1234>` |
| **Output Tokens** | — | `<567>` |
| **Cost (USD)** | — | `<$0.0123>` |
| **Latency (s)** | — | `<7.91>` |
| **Success** | true | `<true/false>` |
| **Output Preview** | — | `<前 200 字符>` |

**填表示例**：

```markdown
实际输出（LLM 修复内容）：
  - **功能**：将 `return a - b` 改为 `return a + b`
  - **diff**：
    ```diff
    -    return a - b  # 故意写错：减号而非加号
    +    return a + b
    ```
测试结果：3/3 通过
Output Quality Score: 5
```

---

### 2.2 Demo 2：知识库 Agent（问内部政策）

| 字段 | 期望值 | 实际值 |
|---|---|---|
| **Case ID** | `demo2_rag` | — |
| **Query** | "我们公司年假政策是什么？" | — |
| **期望行为** | 1. 调 `rag_query` 工具<br>2. 拿到 RAG 返回的引用<br>3. 整合答案 + 引用 | — |
| **期望答案** | 包含 "年假 10 天" + 引用 [`policy.md`] | — |
| **实际答案** | `<实际 LLM 输出>` | — |
| **RAG 引用** | 至少 1 条 `source` 字段 | `<引用数>` |
| **Citation Accuracy** | 1.0 | `<0.0-1.0>` |
| **Output Quality Score** | 4 | `<0-5>` |
| **Input Tokens** | — | `<456>` |
| **Output Tokens** | — | `<123>` |
| **Cost (USD)** | — | `<$0.0045>` |
| **Latency (s)** | — | `<2.13>` |
| **Success** | true | `<true/false>` |

**填表示例**：

```markdown
实际答案：根据公司政策文档 policy.md 第 3.2 节，年假为 10 个工作日。
RAG 引用：1 条（policy.md）
Citation Accuracy: 1.0
Output Quality Score: 5
```

---

### 2.3 Demo 3：数据库 Agent（自然语言问数）

| 字段 | 期望值 | 实际值 |
|---|---|---|
| **Case ID** | `demo3_database` | — |
| **Query** | "上个季度销售额是多少？" | — |
| **期望行为** | 1. 调 `query_database` 工具<br>2. 拿到 SQL + 结果<br>3. 用 ECharts 渲染 | — |
| **期望 SQL** | `SELECT SUM(amount) FROM sales WHERE quarter = ...` | `<实际 SQL>` |
| **实际答案** | 包含具体数字 + ECharts spec | — |
| **Chart Type** | bar / line / pie | `<chart_type>` |
| **Output Quality Score** | 4 | `<0-5>` |
| **Input Tokens** | — | `<789>` |
| **Output Tokens** | — | `<234>` |
| **Cost (USD)** | — | `<$0.0089>` |
| **Latency (s)** | — | `<3.45>` |
| **Success** | true | `<true/false>` |

**填表示例**：

```markdown
实际 SQL：SELECT SUM(amount) FROM sales WHERE quarter = '2026Q2'
实际答案：上个季度（2026Q2）销售额为 ¥1,234,567。
Chart Type: bar
Output Quality Score: 5
```

---

### 2.4 Demo 4：前端操作 Agent（加载 GeoJSON 地图）

| 字段 | 期望值 | 实际值 |
|---|---|---|
| **Case ID** | `demo4_frontend_map` | — |
| **Query** | "加载上海各区疫情热力图" | — |
| **期望行为** | 1. 调 `frontend_tool` (map_load)<br>2. 找到 GeoJSON URL<br>3. WebSocket 推 `FrontendToolCallRequested` | — |
| **期望 GeoJSON** | 上海各区 + 数值字段 | — |
| **实际 GeoJSON URL** | `<实际 URL>` | — |
| **Frontend 事件触发** | `FrontendToolCallRequested` (1 次) | `<true/false>` |
| **Output Quality Score** | 3 | `<0-5>` |
| **Input Tokens** | — | `<567>` |
| **Output Tokens** | — | `<89>` |
| **Cost (USD)** | — | `<$0.0023>` |
| **Latency (s)** | — | `<1.87>` |
| **Success** | true | `<true/false>` |

**填表示例**：

```markdown
实际 GeoJSON URL：https://example.com/shanghai_covid_heatmap.geojson
Frontend 事件触发：true（1 次）
Output Quality Score: 4
```

---

### 2.5 Demo 5：综合多 Agent（政策 + 外部 + 图表 + 团队）

| 字段 | 期望值 | 实际值 |
|---|---|---|
| **Case ID** | `demo5_multi_agent` | — |
| **Query** | "总结公司 Q2 业绩，对比去年同期，给老板做汇报" | — |
| **期望行为** | 1. `BusinessRouter` 路由到多个 Profile<br>2. 调 3+ 业务 Tool<br>3. `SynthesizerRunner` 汇总 | — |
| **调用 Profile** | `rag` + `database` + `synthesizer` | `<实际 Profile 列表>` |
| **调用 Tool** | `rag_query` + `query_database` + `echarts_render` | `<实际 Tool 列表>` |
| **最终答案** | 包含政策 + 数据 + 图表 + 综合总结 | — |
| **Output Quality Score** | 4 | `<0-5>` |
| **Input Tokens** | — | `<1234>` |
| **Output Tokens** | — | `<567>` |
| **Cost (USD)** | — | `<$0.0456>` |
| **Latency (s)** | — | `<8.91>` |
| **Success** | true | `<true/false>` |

**填表示例**：

```markdown
调用 Profile：rag + database + synthesizer
调用 Tool：rag_query (1 次) + query_database (2 次) + echarts_render (1 次)
最终答案：
  - Q2 业绩：总营收 ¥5.6M，同比增长 23%
  - 主要驱动：新客户增长 45%，老客户复购 12%
  - 建议：增加客服投入，应对 45% 新客增长
Output Quality Score: 5
```

---

## 3. 5 Eval Case 路由决策

> **填法**：每条 case 对照 `actual_route` vs `expected_route`。
> **`route_match = true`** 表示路由正确。

| Case ID | 输入 | Expected Route | Actual Route | Route Match | Tokens | Cost (USD) | Latency (s) | Success |
|---|---|---|---|---|---|---|---|---|
| `eval_route_01` | "我们公司年假政策是什么？" | `rag` | `<rag>` | `<true/false>` | `<263>` | `<$0.0009>` | `<1.42>` | `<true/false>` |
| `eval_route_02` | "上海今天天气怎么样？" | `web_search` | `<web_search>` | `<true/false>` | `<198>` | `<$0.0007>` | `<1.13>` | `<true/false>` |
| `eval_route_03` | "上个季度销售额是多少？" | `database` | `<database>` | `<true/false>` | `<245>` | `<$0.0009>` | `<1.51>` | `<true/false>` |
| `eval_route_04` | "总结一下刚才的内容" | `synthesizer` | `<synthesizer>` | `<true/false>` | `<312>` | `<$0.0011>` | `<1.78>` | `<true/false>` |
| `eval_route_05` | "你好" | `general` | `<general>` | `<true/false>` | `<87>` | `<$0.0003>` | `<0.65>` | `<true/false>` |

**汇总**：

- **路由准确率**：`<5/5 (100%)>`
- **平均延迟**：`<1.30>` 秒
- **总 token**：`<1105>`
- **总成本**：`<$0.0039>`

**填表示例**：

```markdown
路由准确率：5/5 (100%)
平均延迟：1.30 秒
总 token：1,105
总成本：$0.0039
```

---

## 4. 简历引用模板

> **直接复制粘贴到简历 / 博客 / GitHub README**。

```markdown
## Real LLM End-to-End Results

> **项目**：kivi-agent（自研 Agent Runtime + 业务 Tool + Web Chat + 长期记忆 + Eval）
> **Wave 8.2 验证**：用真实 LLM 跑通 5 demo + 5 eval case 端到端

### 关键指标

| 维度 | 数值 |
|---|---|
| LLM Provider | <anthropic / openai / deepseek> |
| LLM Model | <claude-sonnet-4-6 / gpt-4o-mini / deepseek-chat> |
| 测试覆盖 | 5 demo + 5 eval case（10/10 通过） |
| 端到端延迟 | <3.42> 秒/case |
| Token 成本 | <$0.0876> / 全量 10 case |
| 路由准确率 | <100%>（5/5 eval case 正确路由） |
| 工具调用准确率 | <100%>（demo 1-5 工具选择正确） |
| RAG 引用准确率 | <100%>（demo 2 引用溯源正确） |

### 演示能力

- **编程 Agent**：LLM 自主修 bug + 跑 pytest，3/3 测试通过
- **知识库 RAG**：LLM 调 `rag_query` + 引用溯源，1.0 引用准确率
- **数据库问数**：LLM 生成 SQL + ECharts 渲染，0 SQL 语法错误
- **前端地图**：LLM 调 `map_load` + WebSocket 推事件，前端实时渲染
- **综合多 Agent**：LLM 路由到 3 个 Profile + 调 3+ 工具 + Synthesizer 汇总

### 复现命令

\`\`\`bash
git clone https://github.com/<你的 handle>/kivi-agent.git
cd kivi-agent
uv sync
cp .env.example .env
# 在 .env 填 KIVI_ANTHROPIC_API_KEY / KIVI_OPENAI_API_KEY
export KIVI_RUN_E2E=1
uv run pytest tests/e2e_real -q
# 报告输出到 reports/e2e_real/
\`\`\`
```

---

## 5. 复现性 checklist

> **填表前自查**——确认这些都做了。

- [ ] 已 `cp .env.example .env` 并填了真实 key
- [ ] 已 export `KIVI_RUN_E2E=1` 和对应 provider 的 key
- [ ] 跑 `uv run pytest tests/e2e_real -q` 全过（10/10）
- [ ] 已生成 `reports/e2e_real/real_llm_run_*.json` 和 `.md`
- [ ] 已 `cat` 或 `jq` 读报告，确认所有字段都有
- [ ] 已填本模板的所有 `<...>` 占位符
- [ ] 已把模板改名为 `RESULTS.md` 并提交到仓库
- [ ] （可选）已在 GitHub README / 简历 / 博客引用

---

## 6. 已知问题与备注

> **如有异常情况，在这里记录**。

### 6.1 失败 case 详情

```
<填法：如有 case 失败，复制失败信息到这里>

例：
eval_route_03 失败：actual_route=database, expected_route=database, 但生成 SQL 语法错误
  → 调整：把 prompt 加 "确保 SQL 符合 PostgreSQL 语法" 后重跑
```

### 6.2 成本偏差

```
<填法：实际成本与预期偏差 >50% 时记录>

例：
demo5 成本 $0.12（预期 $0.05），偏差 +140%
  → 原因：multi-agent 调了 4 个 tool，每次都重新调 LLM
  → 解决：把 KIVI_MAX_STEPS 调到 30
```

### 6.3 延迟偏差

```
<填法：实际延迟与预期偏差 >100% 时记录>

例：
demo1 延迟 15s（预期 5s），偏差 +200%
  → 原因：coding agent 跑了 3 轮迭代修 bug
  → 解决：把 KIVI_E2E_MAX_CASES 限制 demo1 单跑
```

---

## 7. 提交建议

```bash
# 1. 把模板改名
mv docs/e2e-real/RESULTS_TEMPLATE.md docs/e2e-real/RESULTS.md

# 2. 填完所有占位符后
git add docs/e2e-real/RESULTS.md
git commit -m "docs(e2e-real): Wave 8.2 真实 LLM 端到端跑批结果

- Provider: <anthropic>
- Model: <claude-sonnet-4-6>
- Total Cases: 10
- Success Rate: 100%
- Total Cost: \$0.0876
- Avg Latency: 3.42s

Refs: docs/e2e-real/README.md"

# 3. push
git push origin main
```

---

## 附录 A：直接抄的简短版（≤ 200 字）

> **超简短版**，适合放 README / 简历首屏。

```markdown
**Real LLM E2E（Wave 8.2）**：用 <anthropic / openai / deepseek> <claude-sonnet-4-6 / gpt-4o-mini / deepseek-chat>
跑通 5 demo + 5 eval case（10/10 通过），平均延迟 <3.42s>，
全量 10 case 成本 <$0.0876>。详见 docs/e2e-real/RESULTS.md。
```

---

## 附录 B：jq 一键提取报告字段

```bash
# 完整汇总（一行）
cat reports/e2e_real/real_llm_run_*.json | jq '{
  provider: .provider,
  model: .model,
  total_cases: (.cases | length),
  success_rate: ([.cases[] | select(.success)] | length) / (.cases | length),
  total_tokens: ([.cases[].total_tokens] | add),
  total_cost_usd: ([.cases[].cost_usd] | add | . * 10000 | round / 10000),
  avg_latency: ([.cases[].latency_seconds] | add / length | . * 100 | round / 100)
}'

# 路由准确率
cat reports/e2e_real/real_llm_run_*.json | jq '
  [.cases[] | select(.case_id | startswith("eval_route_")) | .route_match] |
  { route_accuracy: (map(select(.)) | length) / length }'
```

---

**维护提示**：

- 本模板随 Wave 8.2 主控集成后**冻结**
- 如未来 L1 / L2 / L3 有新字段（如 streaming 延迟 / 工具调用准确率），同步更新本模板
- 详细填写流程参见 [README.md §8 报告模板](./README.md#8-报告模板)
