# Team + Coding 演示

> Wave 5.2 收口演示：T11 多 Agent 协作 + T12 最小 coding agent，端到端跑通 5 team case + 6 coding case + 10 新 dashboard 端点。

## 数据集

| 文件 | 内容 | 大小 |
|---|---|---|
| `docs/eval-demos/team-5cases.jsonl` | 5 team case：成功 / 接力 / 角色切换 / 部分失败 / 复杂 3 方 | H1 演示 |
| `docs/eval-demos/coding-6cases.jsonl` | 6 coding case：add / fibonacci / reverse_string / parse_url / dedup / sort_dict | H2 演示 |

## T11 多 Agent 协作指标（6 个）

| 指标 | 公式 | 数据来源 |
|---|---|---|
| team_success_rate | 1 if all members success else 0 | member run.finished.status |
| delegation_accuracy | correctly_routed_subtasks / total_subtasks | spec.role vs member role at handoff |
| handoff_quality | successful_messages / total_messages | mailbox write/consume + 状态机一致性 |
| coordination_latency | last_member_finished - team_created | team.created + run.finished |
| agent_utilization | Σ tool_calls / total_steps × members | tool.call_started per member |
| role_consistency | 1 - role_changes / total_steps | role transition events |

## T12 coding Agent 指标（8 个）

| 指标 | 公式 | 数据来源 |
|---|---|---|
| task_completion_rate | final_tests_passed > 0 | coding 循环结束状态 |
| tests_passed_rate | Σ passed / Σ total × iterations | pytest 输出 |
| patch_quality | hunks_applied / hunks_proposed | diff hunk 解析 |
| iteration_count | coding 循环总轮次 | run metadata |
| time_to_first_pass | first_pass_iteration × avg_step_time | run metadata |
| self_recovery_rate | auto_recovered_failures / total_failures | 失败-恢复 pairing |
| compile_success_rate | compile_passed_runs / total_runs | ruff check + mypy |
| test_growth_rate | Σ tests_added / Σ iterations | pytest collect 数量变化 |

## 10 个 Gateway 端点（5 team + 5 coding）

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/team/summary` | 全局统计（team 数 / 成功率 / 平均协调延迟） |
| GET | `/api/team/teams` | team 列表（按 started_at 倒序，分页） |
| GET | `/api/team/teams/{team_id}` | 单 team 全部信息 |
| GET | `/api/team/teams/{team_id}/delegations` | 委派链（from / to / sub_task / ts） |
| GET | `/api/team/teams/{team_id}/metrics` | T11 6 指标 |
| GET | `/api/coding/summary` | 全局统计（run 数 / 完成率 / 平均迭代） |
| GET | `/api/coding/runs` | run 列表（按 started_at 倒序，分页） |
| GET | `/api/coding/runs/{run_id}` | 单 run 全部信息 |
| GET | `/api/coding/runs/{run_id}/patches` | patch 历史 |
| GET | `/api/coding/runs/{run_id}/metrics` | T12 8 指标 |

## CodingAgent 用法（最小版）

```python
from kivi_agent.eval.coding.coding_agent import CodingAgent
from kivi_agent.eval.coding.models import CodingCase, CodingDataset
from kivi_agent.evaluation.fake_llm import FakeLlmProvider

# 1. 加载数据集
dataset = CodingDataset.load(Path("docs/eval-demos/coding-6cases.jsonl"))

# 2. 构造 Agent（注入 LLM + 最大迭代）
llm = FakeLlmProvider()  # 测试用；生产用真实 LLMProvider
agent = CodingAgent(llm=llm, max_iter=3)

# 3. 跑所有 case（每个 case 自动用 tempfile 沙箱）
import asyncio
results = []
for case in dataset.cases:
    result = await agent.run_case(case, sandbox=None)  # sandbox=None → 自动 tmpdir
    results.append(result)

# 4. 算指标
from kivi_agent.eval.metrics import compute_all_coding_metrics
report = compute_all_coding_metrics(results)
print(report.to_dict())
```

**关键约束**：
- 沙箱隔离：`run_case(case, sandbox=None)` 默认用 `tempfile.TemporaryDirectory()`，每次 case 在临时目录跑，**绝不污染主仓库**
- LLM DI：构造时注入 `LLMProvider`；单测用 `FakeLlmProvider`，生产用真实 LLM
- 修复循环：iter=1..max_iter；iter 1 失败 → iter 2 拿 pytest 输出喂 LLM 再修
- pytest cache：每轮清 `__pycache__`，避免 `mymod.pyc` 让第二轮 pytest 看不到源码改动

## 6 个 Web 路由

| 路由 | 视图 |
|---|---|
| `/dashboard/team` | TeamDashboard（summary + list） |
| `/dashboard/team/:teamId` | TeamDashboardDetail（单 team） |
| `/dashboard/team/:teamId/cases/:caseId` | TeamCaseDetail（成员或 sub-task 详情） |
| `/dashboard/coding` | CodingDashboard（summary + list） |
| `/dashboard/coding/:runId` | CodingDashboardDetail（单 run） |
| `/dashboard/coding/:runId/cases/:caseId` | CodingCaseDetail |

## 已知限制

- T11 / T12 真实 LLM 端到端（不依赖 FakeLlmProvider）留 Wave 6 闭环
- T12 sandbox 现在默认 tmpdir，可传 `sandbox: Path` 复用（但调用方负责清理）
- T11 mailbox tracker 监听 `mailbox.write_message` / `consume_messages`；如果业务方用别的 mailbox 实现，需要适配 attach_to
- ECharts 全量引入导致 588KB chunk 警告（Wave 5.1 已知，与本 wave 无关）
