"""kivi-agent 评测数据集（agent: package-eval-dataset-v51）。

Wave 5.1 WT-G1：评测数据集 schema + 批量运行 CLI + Judge 集成。

- EvalCase / EvalDataset：JSONL 数据集（line 1 = 1 case）
- EvalResult / ToolCallRecord / CaseEvent：单 case 运行结果
- EvalRunner：单进程批量运行（asyncio.gather + Semaphore）
- runner_executor：case 执行器（mock 版，WT-G3 集成期换真实 AgentRuntime）
- judge：关键词匹配版（WT-G3 集成期换 LLM Judge，复用 Wave 1 E 包）

**与 Wave 1 E 包边界**：
- 复用 `kivi_agent.evaluation.Judge`（LLM-as-judge），但不强制本包依赖 E 包 Judge
- 本包 Judge 是**离线降级版**（关键词重叠度），用于本地无 LLM 场景跑通
- WT-G3 集成时：把 `judge_case` 切到 E 包 Judge（构造时注入 FakeLlmProvider 跑端到端）

**与 v1 契约关系**：
- 业务 Tool 名：6 个（v1 §1）作为 expected_tools 合法值
- 事件类型：6 个 v1 §5.2.1 事件作为事件流合法 type
- schema_version：1（v1 冻结；不改契约）
"""
from kivi_agent.eval.dataset import EvalCase, EvalDataset
from kivi_agent.eval.result import CaseEvent, EvalResult, ToolCallRecord

__all__ = [
    "CaseEvent",
    "EvalCase",
    "EvalDataset",
    "EvalResult",
    "ToolCallRecord",
]
