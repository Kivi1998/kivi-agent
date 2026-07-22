"""kivi-agent 评测基础设施（Wave 1 / E 阶段）。

按 E 报告（`docs/migration/evaluation-quality-analysis.md`）的拆分：
- 本包实现"运行时 → 评估"的桥（EvalEmitter）
- 共享 Judge 接口（Judge v2 修复：必填 expected_answer + reference_context）
- schema_version 守门（ContractVersion）

**与 core/evaluation/ 的边界**（重要）：
- 本包是**顶层包** `kivi_agent.evaluation`，不是 `kivi_agent.core.evaluation`
- 不依赖 core/ 内部实现细节（仅依赖 EventBus + 事件类）
- A 阶段修改 `core/` 不会污染本包；本包扩展不会污染 A 阶段

**演示版**（当前阶段）：
- EvalEmitter 默认 JSONL 落地（无需 redis/asyncpg/PostgreSQL）
- Redis Streams 路径**可选开关**，缺包时降级到 JSONL，绝不 hard-fail
"""
from kivi_agent.evaluation.contract_version import (
    ContractVersionMismatchError,
    assert_schema_version,
    current_schema_version,
)
from kivi_agent.evaluation.emitter import (
    EvalEmitter,
    EvalEmitterConfig,
    JsonlEmitterBackend,
    RedisStreamsEmitterBackend,  # 可选，缺包时为 None
    redis_available,
)
from kivi_agent.evaluation.judge import Judge, JudgeResult

__all__ = [
    "ContractVersionMismatchError",
    "EvalEmitter",
    "EvalEmitterConfig",
    "Judge",
    "JudgeResult",
    "JsonlEmitterBackend",
    "RedisStreamsEmitterBackend",
    "assert_schema_version",
    "current_schema_version",
    "redis_available",
]
