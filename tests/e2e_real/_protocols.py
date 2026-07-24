"""真实 LLM E2E 测试的最小 Protocol 集合（agent: package-e2e-real-w82）。

# _protocols.py（agent: package-e2e-real-w82）
WT-L3 E2E 框架设计要点：
- 不 import `kivi_agent.core.llm.provider` (L1) 或 `openai_compat_provider` (L2)
  （L1/L2 在本 worktree baseline 不存在；主控集成期会拼回）
- 用 Protocol 定义 fixture 与 e2e test 之间的最小契约
- 集成期 main agent 在 e2e 框架外用真实 provider 实现这个 Protocol

只放类型/接口，**不**放任何业务逻辑；fixture 与测试用这个 Protocol 做签名约束。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMCompleteResult:
    """单次 LLM 调用的最小结果（input/output tokens + text）。"""

    text: str
    input_tokens: int
    output_tokens: int


class LLMSimpleProvider(Protocol):
    """真实 LLM 端到端测试用的最小 provider 协议。

    设计要点：
    - `provider_name` / `model_name` 用于报告 / 成本计算
    - `complete(prompt)` 是单轮调用的最小入口（不含工具调用 / 流式）
    - 不抛异常的"业务失败"应通过 `text=""` 或返回带 `error` 字段的字符串表达
    """

    provider_name: str
    model_name: str

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
    ) -> LLMCompleteResult: ...


__all__ = [
    "LLMCompleteResult",
    "LLMSimpleProvider",
]
