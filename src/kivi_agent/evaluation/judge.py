"""Judge — LLM-as-judge 评估器（Wave 1 / E 阶段 T4 修复版）。

修复要点（E 报告 §T9 + 风险 2）：
- `expected_answer` 必填，不再可选
- `reference_context` 必填（list[str]），不再可选
- prompt_template 必须**显式引用**这两个字段，否则导入期 assertion 失败
- 演示版 JudgeResult 是 dataclass（无 pydantic 依赖），含 score / reasoning / passed

**与 aigroup 旧 Judge 的差异**：
- aigroup `_JUDGE_PROMPT` 完全没读 `expected_answer` / `reference_context`，
  导致评分纯靠 LLM 主观——这正是 E 报告强调的"LLM Judge 自说自话"风险
- 修复后：prompt 模板**必须**含 `{expected_answer}` 与 `{reference_context}` 占位符
- 单元测试 `test_judge.py` 验证 prompt 实际填充了这两个字段
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from kivi_agent.core.llm.types import LlmResponse


class _LLMProviderLike(Protocol):
    """LLM Provider 协议（最小子集，Judge 只需要 chat 接口）。"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: Any,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse: ...


@dataclass
class JudgeResult:
    """Judge 评估结果。

    字段：
    - score: 0.0-1.0 之间的综合分（composite）
    - reasoning: 评分理由（≤200 字）
    - passed: 是否通过（演示版用 score >= 0.6 阈值）

    不引入 pydantic，保持与 E 报告的 dataclass 风格一致。
    """

    score: float
    reasoning: str
    passed: bool
    # 原始 LLM 响应（保留供调试 / ragas 复评）
    raw: dict[str, Any] = field(default_factory=dict)


#: 默认 prompt 模板（演示版）
#: 关键：必须含 {expected_answer} 与 {reference_context} 占位符
DEFAULT_PROMPT_TEMPLATE: str = """你是一个严格的智能体回答质量评估专家。

【任务】
对比"标准答案"和"参考答案上下文"，评估"智能体回答"的质量。

【输入】
- 用户问题：{question}
- 智能体回答：{actual_answer}
- 标准答案（Ground Truth）：{expected_answer}
- 参考答案上下文（用于查证引用和忠实度）：{reference_context}

【评估维度】（0.0 - 1.0 或 bool）
1. correctness：actual_answer 与 expected_answer 关键事实一致性
2. completeness：expected_answer 要点覆盖度
3. hallucination：actual_answer 是否包含 reference_context/expected_answer 都不支持的内容
4. format_compliant：输出是否结构清晰
5. citation_accuracy（如有引用）：引用 ID 是否在 reference_context 中存在

【输出 JSON（严格按此格式，不要代码块包裹）】
{{
  "correctness": 0.0,
  "completeness": 0.0,
  "hallucination": false,
  "format_compliant": true,
  "citation_accuracy": 0.0,
  "reasoning": "≤200 字，给出扣分理由"
}}
"""


class Judge:
    """LLM-as-judge 评估器。

    接口（与 E 报告 §T9 一致）：
        judge = Judge(llm_provider=provider, prompt_template=DEFAULT_PROMPT_TEMPLATE)
        result = await judge.evaluate(
            question="...",
            actual_answer="...",
            expected_answer="...",         # 必填
            reference_context=["..."],     # 必填（list[str]）
        )

    关键约束：
    - `expected_answer` 与 `reference_context` **位置参数必填**（无默认值）
    - `prompt_template` 缺失 `{expected_answer}` 或 `{reference_context}` 占位符时，
      构造期直接抛 ValueError（fail-fast）
    """

    #: 必填占位符（用于构造期校验）
    REQUIRED_PLACEHOLDERS: tuple[str, ...] = ("{expected_answer}", "{reference_context}")

    #: 默认通过阈值（composite score >= threshold 视为 passed）
    DEFAULT_PASS_THRESHOLD: float = 0.6

    def __init__(
        self,
        *,
        llm_provider: _LLMProviderLike,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    ) -> None:
        self._llm = llm_provider
        # 构造期校验：占位符必须齐全（fail-fast）
        missing = [p for p in self.REQUIRED_PLACEHOLDERS if p not in prompt_template]
        if missing:
            raise ValueError(
                f"Judge prompt_template 缺少必填占位符: {missing}\n"
                f"  E 报告 §T9 修复要求：prompt 必须显式使用 expected_answer + reference_context\n"
                f"  当前模板: {prompt_template[:200]!r}..."
            )
        self._prompt_template = prompt_template
        self._pass_threshold = pass_threshold

    # 单条评估入口
    async def evaluate(
        self,
        *,
        question: str,
        actual_answer: str,
        expected_answer: str,        # 必填
        reference_context: list[str],  # 必填
    ) -> JudgeResult:
        """对单条 (question, actual_answer) 打分。

        参数：
            question: 用户问题
            actual_answer: 智能体回答
            expected_answer: 标准答案（Ground Truth），必填
            reference_context: 参考答案上下文（list[str]），必填

        返回：
            JudgeResult（含 score / reasoning / passed）
        """
        # 构造 prompt（确保 expected_answer / reference_context 被显式注入）
        context_text = "\n\n".join(reference_context) if reference_context else "（无）"
        prompt = self._prompt_template.format(
            question=question,
            actual_answer=actual_answer,
            expected_answer=expected_answer or "（无标准答案）",
            reference_context=context_text,
        )

        # 调 LLM（演示版：直接走 provider.chat，不订阅 EventBus）
        from kivi_agent.core.events.bus import EventBus

        bus = EventBus()
        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tool_schemas=[],
            bus=bus,
            run_id="judge-eval",
        )

        # 解析 LLM 输出
        parsed = _parse_judge_response(response.text)
        score = _calc_composite(parsed)
        return JudgeResult(
            score=score,
            reasoning=parsed.get("reasoning", ""),
            passed=score >= self._pass_threshold,
            raw=parsed,
        )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

# 从 LLM 文本响应中提取 JSON（演示版：找第一个 { 到最后一个 }）
def _parse_judge_response(text: str) -> dict[str, Any]:
    """宽松解析 LLM 输出的 JSON dict。

    演示版策略：找第一个 `{` 到最后一个 `}`，中间 load 为 dict。
    不做 markdown 代码块剥离（已通过 prompt 禁止）。
    """
    import json

    text = text.strip()
    if not text:
        return {}
    first = text.find("{")
    last = text.rfind("}")
    if first < 0 or last <= first:
        return {"_raw": text, "_parse_error": "no_json_braces"}
    snippet = text[first : last + 1]
    try:
        result: dict[str, Any] = json.loads(snippet)
        return result
    except json.JSONDecodeError as exc:
        return {"_raw": text, "_parse_error": str(exc)}


# 计算 composite score（演示版公式）
def _calc_composite(parsed: dict[str, Any]) -> float:
    """演示版 composite 公式：与 E 报告 §T9 v2 公式一致。

    composite = correctness * 40 + completeness * 25
              + (0 if hallucination else 10) + (5 if format_compliant else 0)
              + citation_accuracy * 20
    范围：0-100，输出 0-1 归一化。
    """
    correctness = float(parsed.get("correctness", 0.0))
    completeness = float(parsed.get("completeness", 0.0))
    hallucination = bool(parsed.get("hallucination", True))
    format_compliant = bool(parsed.get("format_compliant", False))
    citation_accuracy = float(parsed.get("citation_accuracy", 0.0))

    raw = (
        correctness * 40
        + completeness * 25
        + (0 if hallucination else 10)
        + (5 if format_compliant else 0)
        + citation_accuracy * 20
    )
    return round(raw / 100.0, 4)
