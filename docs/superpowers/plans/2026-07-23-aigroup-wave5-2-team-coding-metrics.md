# aigroup Wave 5.2：T11 多 Agent 协作指标 + T12 coding Agent 指标

> **基线**：`main @ 94a1b84`（aigroup Wave 5.1 收官，1070 passed / 206 files / Eval + Dashboard）
> **日期**：2026-07-23
> **承接关系**：Wave 5.1 已落 Eval 基础 + 7 指标 + Dashboard。Wave 5.2 在其上加 T11（多 Agent 协作）和 T12（coding Agent）两个高级场景的指标 + 视图。
> **用户决定（2026-07-23）**：
>   1. 一波做完 T11 + T12（不拆 5.2.1 / 5.2.2）
>   2. T12 coding Agent = kivi 自建最小版本，**不**接 aigroup coding 模式

---

## 一、目标

让 kivi-agent 从"可评测的单 Agent"进入"**可评测的多 Agent 团队 + 可评测的代码生成**"：

```
现有（Wave 5.1）
  EvalCase → EvalRunner → EvalResult + 7 基础指标
新增（Wave 5.2）
  TeamCase → TeamRunner → TeamResult  + 6 T11 指标
  CodingCase → CodingRunner → CodingResult + 8 T12 指标
```

**核心交付**：
- 6 个 T11 指标：team_success / delegation_accuracy / handoff_quality / coordination_latency / agent_utilization / role_consistency
- 8 个 T12 指标：task_completion / tests_passed / patch_quality / iteration_count / time_to_first_pass / self_recovery / compile_success / test_growth
- 最小 coding agent（kivi 内）：接受 spec → 改文件 → 跑 pytest → 失败则再修 → 循环
- Dashboard 后端：5 team 端点 + 5 coding 端点
- Dashboard 前端：2 新视图（TeamPlan / CodingRun）+ 路由
- 演示数据集 + 集成 + 文档

---

## 二、范围

### 2.1 必做（Wave 5.2 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| H1 | T11 多 Agent 协作追踪 + 6 指标 + 演示数据集 | 2-3 天 | `src/kivi_agent/eval/team_*.py` + `metrics/team.py` + `tests/` |
| H2 | T12 最小 coding agent + 8 指标 + 演示数据集 | 2-3 天 | `src/kivi_agent/eval/coding_*.py` + `metrics/coding.py` + `tests/` |
| H3 | Dashboard 后端扩展（10 新端点） | 2 天 | `src/kivi_agent/gateway/{team,coding}_dashboard.py` + `eval/team_store.py` + `eval/coding_store.py` + tests |
| H4 | Dashboard 前端扩展（2 新视图 + 路由） | 2-3 天 | `apps/web-chat/src/{views,components}/TeamPlan*` + `CodingRun*` + 路由 + tests |
| 主控 | 集成 + 文档 + 演示数据 + 全量验证 | 1-2 天 | 集成 commit + `docs/eval-demos/` + 收口记录 |

**总估时**：9-13 天，4 WT 并行 + 集成

### 2.2 T11 6 个指标（Wave 5.2 必做）

| 指标 | 公式 | 数据来源 |
|---|---|---|
| team_success_rate | 1 if all members success else 0 | member run.finished.status |
| delegation_accuracy | `correctly_routed_subtasks / total_subtasks` | spec.role vs member role at handoff |
| handoff_quality | `successful_messages / total_messages` | mailbox write/consume + 状态机一致性 |
| coordination_latency | last_member_finished - team_created | team.created + run.finished |
| agent_utilization | Σ tool_calls / total_steps × members | tool.call_started per member |
| role_consistency | 1 - role_changes / total_steps | role transition events |

### 2.3 T12 8 个指标（Wave 5.2 必做）

| 指标 | 公式 | 数据来源 |
|---|---|---|
| task_completion_rate | final_tests_passed > 0 | coding 循环结束状态 |
| tests_passed_rate | Σ passed / Σ total × iterations | pytest 输出 |
| patch_quality | hunks_applied / hunks_proposed | diff hunk 解析 |
| iteration_count | coding 循环总轮次 | run metadata |
| time_to_first_pass | first_pass_iteration × avg_step_time | run metadata |
| self_recovery_rate | `auto_recovered_failures / total_failures` | 失败-恢复 pairing |
| compile_success_rate | `compile_passed_runs / total_runs` | 静态检查（ruff check + mypy） |
| test_growth_rate | `Σ tests_added / iterations` | pytest collect 数量变化 |

### 2.4 T12 最小 coding agent 设计

```python
class CodingAgent:
    """最小 coding agent（kivi 内）。

    流程（per case）：
      1. 接受 spec: { task, test_file, max_iter=3 }
      2. LLM 生成 patch（FakeLlmProvider 跑单测）
      3. 应用 patch 到 sandbox 目录
      4. 跑 pytest 收集结果
      5. 如失败且 iter < max_iter：把 pytest 输出喂给 LLM 再修，回到 2
      6. 返回 CodingRunResult
    """
    async def run_case(self, case: CodingCase, llm: LlmProvider, sandbox: Path) -> CodingRunResult
```

**关键约束**：
- **不**接 aigroup 真实 coding agent（用户决定，2026-07-23）
- sandbox 隔离：每次 case 在临时目录跑，避免污染主仓库
- LLM 可注入：单测用 `FakeLlmProvider` 跑

### 2.5 v1 契约边界

- 不修改 v1 §1（6 业务 Tool 名）
- 不修改 v1 §5.2.1 现有 6 事件
- **允许新增**（与 Wave 1 加 RunCancelledEvent 同样规则）：
  - 数据类：`TeamEvalResult` / `CodingEvalResult` / `DelegationStep` / `MemberOutcome` / `PatchRecord` / `TestResult`
  - 复用 `EvalResult` 的 `events` / `tool_calls` 字段记录所有委派/接力信息（避免新增 v1 事件）
- v1 §4 tool name 列表里**不**新增 `coding_run` / `team_run`（它们是评测执行器，不是业务 Tool）

---

## 三、4 个 WT 详细设计

### WT-H1: T11 多 Agent 协作追踪 + 6 指标

**目标**：能跑 team plan，收集 6 个 T11 指标，端到端打 0 集成期依赖

**代码位置**：
- `src/kivi_agent/eval/team/__init__.py`
- `src/kivi_agent/eval/team/models.py`：`TeamCase` / `TeamEvalResult` / `DelegationStep` / `MemberOutcome`
- `src/kivi_agent/eval/team/team_runner.py`：TeamRunner（asyncio + Semaphore）+ team_executor
- `src/kivi_agent/eval/team/mailbox_tracker.py`：mailbox 写消费监听（注入 TeamManager）
- `src/kivi_agent/eval/metrics/team.py`：6 指标

**JSONL 字段**：
```json
{
  "id": "team-01",
  "goal": "调研并对比 X 和 Y 框架",
  "member_specs": [{"name": "researcher", "role": "research"}, {"name": "writer", "role": "writer"}],
  "sub_tasks": [{"assignee": "researcher", "topic": "X 框架"}, {"assignee": "writer", "topic": "汇总"}],
  "expected_assignments": {"researcher": 1, "writer": 1},
  "expected_total_messages": 4,
  "max_steps_per_member": 20,
  "difficulty": "medium"
}
```

**演示数据集**：`docs/eval-demos/team-5cases.jsonl`（5 个 team case 覆盖成功/失败/接力/角色切换）

**测试**：
- `tests/unit/test_team_models.py`（5 case 数据类 + 路径遍历）
- `tests/unit/test_team_runner.py`（mock 跑 / 失败隔离 / 邮箱追踪 8 case）
- `tests/unit/test_metrics_team.py`（6 指标 × 3 fixture ≈ 18 case）
- `tests/integration/test_team_run.py`（端到端 5 case，期望 4-5 通过）

**commit 规划**：6-7 commit
1. `feat(eval): TeamCase / TeamEvalResult 数据类 + JSONL 加载 + 路径遍历保护`
2. `feat(eval): mailbox tracker（mailbox 写消费 → 事件流）`
3. `feat(eval): TeamRunner + team_executor（异步并发 + 失败隔离）`
4. `feat(metrics): T11 6 指标 + JSON 输出 + 路径遍历保护`
5. `test(team): 5 case 数据集 + 单测 + 集成测试`
6. `docs(team): 演示数据集 docs/eval-demos/team-5cases.jsonl`
7. `fix(team): 集成期 mypy 收尾（如需）`

### WT-H2: T12 最小 coding agent + 8 指标

**目标**：自建最小 coding agent，能跑 patch → pytest → 修复循环，收集 8 个 T12 指标

**代码位置**：
- `src/kivi_agent/eval/coding/__init__.py`
- `src/kivi_agent/eval/coding/models.py`：`CodingCase` / `CodingEvalResult` / `PatchRecord` / `TestRunRecord`
- `src/kivi_agent/eval/coding/coding_agent.py`：CodingAgent（最小版本，patch 写文件 + pytest + 循环）
- `src/kivi_agent/eval/coding/diff_parser.py`：unified diff hunk 解析
- `src/kivi_agent/eval/metrics/coding.py`：8 指标

**JSONL 字段**：
```json
{
  "id": "code-01",
  "task": "Write a function add(a, b) that returns a + b",
  "test_file": "tests/test_add.py",
  "test_content": "from mymod import add\ndef test_add(): assert add(1, 2) == 3",
  "initial_file": "mymod.py",
  "initial_content": "# empty",
  "expected_function": "add",
  "expected_tests_count": 1,
  "max_iter": 3,
  "difficulty": "easy"
}
```

**CodingAgent 接口**：
```python
class CodingAgent:
    def __init__(self, llm: LlmProvider, max_iter: int = 3):
        self._llm = llm
        self._max_iter = max_iter

    async def run_case(self, case: CodingCase, sandbox: Path) -> CodingEvalResult:
        """单 case 跑 coding 循环，返回结果。"""
```

**演示数据集**：`docs/eval-demos/coding-6cases.jsonl`（6 个编程 case：add / fibonacci / reverse_string / parse_url / dedup / sort_dict）

**测试**：
- `tests/unit/test_coding_models.py`（数据类 + 路径遍历）
- `tests/unit/test_diff_parser.py`（unified diff 解析 8 case）
- `tests/unit/test_coding_agent.py`（mock LLM + 真实 pytest × 6 case）
- `tests/unit/test_metrics_coding.py`（8 指标 × 3 fixture ≈ 24 case）
- `tests/integration/test_coding_run.py`（端到端 6 case 跑通 ≥ 4）

**commit 规划**：6-7 commit
1. `feat(eval): CodingCase / CodingEvalResult / PatchRecord / TestRunRecord`
2. `feat(eval): diff_parser（unified diff hunk 解析）`
3. `feat(eval): CodingAgent 最小实现（patch + pytest + 修复循环）`
4. `feat(metrics): T12 8 指标 + JSON 输出 + 路径遍历保护`
5. `test(coding): 6 case 数据集 + 单测 + 集成测试`
6. `docs(coding): 演示数据集 docs/eval-demos/coding-6cases.jsonl`
7. `fix(coding): 集成期 mypy 收尾（如需）`

### WT-H3: Dashboard API 扩展（10 新端点）

**目标**：复用 EvalResultStore 模式，新增 team / coding 端点

**代码位置**：
- `src/kivi_agent/eval/team_store.py`：`TeamResultStore`（JSONL + 路径遍历保护）
- `src/kivi_agent/eval/coding_store.py`：`CodingResultStore`
- `src/kivi_agent/gateway/team_dashboard.py`：5 端点
  - `GET /api/team/summary`
  - `GET /api/team/teams`
  - `GET /api/team/teams/{team_id}`
  - `GET /api/team/teams/{team_id}/delegations`
  - `GET /api/team/teams/{team_id}/metrics`
- `src/kivi_agent/gateway/coding_dashboard.py`：5 端点
  - `GET /api/coding/summary`
  - `GET /api/coding/runs`
  - `GET /api/coding/runs/{run_id}`
  - `GET /api/coding/runs/{run_id}/patches`
  - `GET /api/coding/runs/{run_id}/metrics`
- `src/kivi_agent/gateway/main.py`：挂载 2 个新 router

**测试**：
- `tests/unit/test_team_store.py`（5 场景）
- `tests/unit/test_coding_store.py`（5 场景）
- `tests/unit/test_team_dashboard_api.py`（5 端点 × 2 场景 = 10 case）
- `tests/unit/test_coding_dashboard_api.py`（5 端点 × 2 场景 = 10 case）
- `tests/integration/test_dashboard_team_e2e.py`（端到端 3 case）
- `tests/integration/test_dashboard_coding_e2e.py`（端到端 3 case）

**commit 规划**：4-5 commit
1. `feat(eval): TeamResultStore / CodingResultStore（JSONL 追加写 + 路径遍历保护）`
2. `feat(gateway): team_dashboard 5 端点 + main.py 挂载`
3. `feat(gateway): coding_dashboard 5 端点 + main.py 挂载`
4. `test(dashboard): team + coding 端点 + store 单测 + 6 集成测试`
5. `fix(gateway): 集成期 mypy 收尾（如需）`

### WT-H4: Dashboard 前端扩展

**目标**：Vue 3 + 2 新视图 + 路由

**代码位置**：
- `apps/web-chat/src/api/team_dashboard.ts`（5 端点 + 类型）
- `apps/web-chat/src/api/coding_dashboard.ts`（5 端点 + 类型）
- `apps/web-chat/src/components/team/`
  - `TeamSummaryCard.vue`
  - `TeamsList.vue`
  - `DelegationTree.vue`（简易委派树：成员 → 委派 sub-task → 完成状态）
  - `RoleTimeline.vue`（成员角色时间线）
  - `MemberOutcomesTable.vue`
- `apps/web-chat/src/components/coding/`
  - `CodingSummaryCard.vue`
  - `RunsList.vue`
  - `PatchDiffViewer.vue`（轻量级 diff viewer，不上 monaco）
  - `TestHistoryTimeline.vue`
  - `IterationCountBadge.vue`
- `apps/web-chat/src/views/TeamDashboard.vue` / `TeamDashboardDetail.vue` / `TeamCaseDetail.vue`
- `apps/web-chat/src/views/CodingDashboard.vue` / `CodingDashboardDetail.vue`
- `apps/web-chat/src/router.ts`：加 6 个新路由
- `apps/web-chat/src/types/api.ts`：追加 team + coding 类型

**测试**：
- `dashboard.spec.ts` 扩展 + 5 个 spec × 2-3 case
- type-check / lint / build 全绿

**commit 规划**：4-5 commit
1. `feat(web-chat): team + coding API 客户端 + 类型`
2. `feat(web-chat): 5 team widget + 5 coding widget`
3. `feat(web-chat): 3 team view + 2 coding view`
4. `feat(web-chat): router 加 6 个 dashboard 子路由（team/* + coding/*）`
5. `style(web-chat): lint --fix（如需）`

---

## 四、4 个 WT 集成顺序

```
H1 (team runner/metrics)  ─┐
H2 (coding agent/metrics) ─┼─→ H3 (gateway) → H4 (frontend) → 主控集成
H3 (gateway 独立)         ─┘
H4 (frontend 独立，依赖 H3 类型)
```

**主控集成顺序**：
1. cherry-pick / rebase H1 → H2 → H3 → H4 到 `integration/aigroup-wave5-2`
2. 集成期修复（H1/H2/H3 间接口冲突、跨包 import 顺序、mypy 收尾）
4. 全量验证：pytest / mypy / ruff / 前端 type-check / test / lint / build
5. demo 数据集：跑 5 team case + 6 coding case，确认 5 team 端点 + 5 coding 端点返回值
6. 文档：`docs/eval-demos/team-coding-README.md` + 收口记录
7. 合并 main + 推 GitHub + 清理 worktree

---

## 五、风险与边界

| 风险 | 缓解 |
|---|---|
| T11 team plan 没有真实多 LLM 实例 | 单元测试用 FakeLlmProvider 跑 1 步；端到端跑 1-2 个真实 LLM case 留 Wave 6 |
| T12 coding agent 沙箱隔离 | 用 `tempfile.TemporaryDirectory`；不在主仓库写文件 |
| T12 coding agent LLM 调用会真实扣 token | 单测用 FakeLlmProvider；集成测试用 1 case 真实 LLM 留 Wave 6 |
| H4 前端体量大 | 5+5 widget + 5 view，比 Wave 5.1 G4 略大；拆 5 commit 渐进 |
| H3 端点 schema 与 H1/H2 类型不一致 | 主控集成期核对 `TeamEvalResult` / `CodingEvalResult` schema |
| v1 事件不新增 | 用 EvalResult.events 字段存 team + coding 事件流；不破坏 v1 §5.2.1 |

---

## 六、收口判定

- [ ] 后端 pytest 全绿（基线 1070 + Wave 5.2 新增 ≥ 50）
- [ ] mypy 0 / ≥ 220 files（206 + 14-20 新文件）
- [ ] ruff 与 Wave 5.1 收口基线持平（45，**Wave 5.2 新增 0**）
- [ ] 前端 type-check / test / lint / build 全绿
- [ ] T11 演示数据集 + 5 端点 dashboard 端到端跑通
- [ ] T12 演示数据集 + 5 端点 dashboard 端到端跑通
- [ ] 收口记录 + 演示文档
- [ ] 4 个 Wave 5.2 worktree 合并后清理
- [ ] Ruff pre-existing 45 项基线（不阻塞 Wave 5.2 关闭）
- [ ] T12 真实 LLM 端到端（Wave 6 闭环）

---

## 七、Wave 5.2 → 后续

- **Wave 6**：Vector Memory（V7 长时记忆 + 语义检索）
- **Wave 7**：真实 rag-kb 端到端 + 部署 + 演示

Wave 5.2 完成后，kivi-agent 评测系统覆盖：单 Agent（Wave 5.1）+ 多 Agent 协作（Wave 5.2 T11）+ 代码生成（Wave 5.2 T12），为 Wave 6 高级 Memory 提供观测依据。
