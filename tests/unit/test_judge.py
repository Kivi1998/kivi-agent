"""Judge 单元测试（Wave 1 / E 阶段 T4 修复版）。

核心目标（E 报告 §T9 + 风险 2）：
1. 验证 prompt 必含 {expected_answer} + {reference_context}（构造期 fail-fast）
2. 验证 evaluate() 必填参数；不传 → TypeError
3. 验证 prompt 实际填充了 expected_answer + reference_context 内容
4. 验证 JudgeResult 字段（score / reasoning / passed）

关键：E 报告强调"LLM Judge 自说自话"风险——本测试**不仅测 LLM 输出**，
更测**LLM 拿到的 prompt 是否真的引用了 ground truth 与 reference context**。
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from kivi_agent.evaluation import Judge, JudgeResult
from kivi_agent.evaluation.judge import (
    DEFAULT_PROMPT_TEMPLATE,
    _calc_composite,
    _parse_judge_response,
)
from tests._fakes import FakeLlmProvider, LlmScriptedResponse


# ---- 必填占位符守门 -------------------------------------------------------

# 功能：验证默认 prompt 模板必含两个关键占位符
# 设计：直接断言字符串包含；防止 E 阶段后续 Agent 改坏 prompt 模板
def test_default_prompt_template_has_required_placeholders() -> None:
    assert "{expected_answer}" in DEFAULT_PROMPT_TEMPLATE
    assert "{reference_context}" in DEFAULT_PROMPT_TEMPLATE


# 功能：验证 Judge 构造时缺占位符立即抛 ValueError
# 设计：传入无 expected_answer 占位符的模板，构造期 fail-fast
def test_judge_rejects_prompt_missing_expected_answer() -> None:
    provider = FakeLlmProvider()
    bad_template = "你是评分员。问题：{question}。回答：{actual_answer}。"

    with pytest.raises(ValueError, match="expected_answer"):
        Judge(llm_provider=provider, prompt_template=bad_template)


# 功能：验证 Judge 构造时缺 reference_context 占位符立即抛 ValueError
# 设计：与上一条对照，覆盖另一占位符
def test_judge_rejects_prompt_missing_reference_context() -> None:
    provider = FakeLlmProvider()
    bad_template = (
        "你是评分员。问题：{question}。"
        "回答：{actual_answer}。答案：{expected_answer}。"
    )

    with pytest.raises(ValueError, match="reference_context"):
        Judge(llm_provider=provider, prompt_template=bad_template)


# 功能：验证 Judge 构造时两个占位符都齐全则通过
# 设计：补全占位符，构造不抛
def test_judge_accepts_prompt_with_both_placeholders() -> None:
    provider = FakeLlmProvider()
    ok_template = (
        "问题：{question}\n"
        "回答：{actual_answer}\n"
        "标准答案：{expected_answer}\n"
        "上下文：{reference_context}\n"
    )
    judge = Judge(llm_provider=provider, prompt_template=ok_template)
    assert judge is not None


# ---- evaluate() 必填参数 ---------------------------------------------------

# 功能：验证 evaluate() 缺 expected_answer 抛 TypeError
# 设计：Python 关键字参数签名保护；缺则必抛
async def test_evaluate_requires_expected_answer_kwarg() -> None:
    provider = FakeLlmProvider()
    judge = Judge(llm_provider=provider)

    with pytest.raises(TypeError):
        await judge.evaluate(  # type: ignore[call-arg]
            question="q",
            actual_answer="a",
            reference_context=["ctx"],
        )


# 功能：验证 evaluate() 缺 reference_context 抛 TypeError
# 设计：同上，覆盖另一必填参数
async def test_evaluate_requires_reference_context_kwarg() -> None:
    provider = FakeLlmProvider()
    judge = Judge(llm_provider=provider)

    with pytest.raises(TypeError):
        await judge.evaluate(  # type: ignore[call-arg]
            question="q",
            actual_answer="a",
            expected_answer="exp",
        )


# ---- prompt 实际填充验证 ---------------------------------------------------

# 功能：验证 evaluate() 调 LLM 时 prompt 含 expected_answer 的实际内容
# 设计：用 FakeLlmProvider 拦截 prompt，检查 LLM 真的看到 expected_answer
async def test_evaluate_injects_expected_answer_into_prompt() -> None:
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text='{"correctness":1.0}', stop_reason="end_turn")]
    )
    judge = Judge(llm_provider=provider)

    await judge.evaluate(
        question="中国的首都是哪里？",
        actual_answer="北京",
        expected_answer="北京",
        reference_context=["北京是中华人民共和国的首都。"],
    )

    assert provider.call_count == 1
    # 拦截 LLM 实际拿到的 user message
    user_msg = provider.last_messages[0]
    content_str = str(user_msg["content"])
    assert "北京" in content_str
    # 关键断言：expected_answer 字段的实际值出现在 prompt
    # 而非占位符本身
    assert "{expected_answer}" not in content_str
    assert "{reference_context}" not in content_str


# 功能：验证 evaluate() 调 LLM 时 prompt 含 reference_context 的实际内容
# 设计：同上，覆盖另一字段
async def test_evaluate_injects_reference_context_into_prompt() -> None:
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text='{"correctness":1.0}', stop_reason="end_turn")]
    )
    judge = Judge(llm_provider=provider)

    ctx_text = "中华人民共和国成立于 1949 年 10 月 1 日"
    await judge.evaluate(
        question="Q?",
        actual_answer="A",
        expected_answer="E",
        reference_context=[ctx_text],
    )

    content = str(provider.last_messages[0]["content"])
    assert ctx_text in content


# 功能：验证 reference_context 多个片段被 join 到 prompt
# 设计：传 3 个 context 片段，断言都出现
async def test_evaluate_injects_all_reference_context_chunks() -> None:
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text='{"correctness":0.5}')]
    )
    judge = Judge(llm_provider=provider)

    await judge.evaluate(
        question="Q",
        actual_answer="A",
        expected_answer="E",
        reference_context=["chunk-1", "chunk-2", "chunk-3"],
    )

    content = str(provider.last_messages[0]["content"])
    for chunk in ("chunk-1", "chunk-2", "chunk-3"):
        assert chunk in content, f"reference_context 片段缺失: {chunk}"


# 功能：验证 reference_context 为空列表时 prompt 不崩溃
# 设计：空 list 是合法输入（E 报告说开放式问题可无上下文）
async def test_evaluate_handles_empty_reference_context() -> None:
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text='{"correctness":0.5}')]
    )
    judge = Judge(llm_provider=provider)

    result = await judge.evaluate(
        question="Q",
        actual_answer="A",
        expected_answer="E",
        reference_context=[],
    )
    assert isinstance(result, JudgeResult)


# ---- JudgeResult 字段 ------------------------------------------------------

# 功能：验证 JudgeResult.score 在 0-1 范围
# 设计：复合公式归一化到 0-1；构造几个典型 LLM 响应验证
def test_composite_score_normalized_to_zero_one() -> None:
    # 满分
    assert _calc_composite({
        "correctness": 1.0, "completeness": 1.0,
        "hallucination": False, "format_compliant": True,
        "citation_accuracy": 1.0,
    }) == 1.0
    # 零分
    assert _calc_composite({
        "correctness": 0.0, "completeness": 0.0,
        "hallucination": True, "format_compliant": False,
        "citation_accuracy": 0.0,
    }) == 0.0
    # 缺字段：宽容处理
    assert _calc_composite({}) == 0.0
    assert _calc_composite({"correctness": 0.5}) == 0.5 * 40 / 100  # = 0.2


# 功能：验证 LLM 响应中的 JSON 被正确解析
# 设计：标准 JSON、含 markdown 包裹、嵌套 dict 都应解析
def test_parse_judge_response_handles_typical_llm_outputs() -> None:
    # 标准 JSON
    parsed = _parse_judge_response('{"correctness": 0.8}')
    assert parsed == {"correctness": 0.8}
    # 含前导文字 + JSON
    parsed = _parse_judge_response('评价结果：{"correctness": 0.8, "reasoning": "ok"}')
    assert parsed["correctness"] == 0.8
    assert parsed["reasoning"] == "ok"
    # 无 JSON：返回 _raw
    parsed = _parse_judge_response("no json here")
    assert "_raw" in parsed
    assert parsed["_raw"] == "no json here"
    # 空字符串
    assert _parse_judge_response("") == {}


# 功能：验证 evaluate() 端到端返回 JudgeResult
# 设计：FakeLlmProvider 返回已知 JSON；断言 JudgeResult 字段被填充
async def test_evaluate_returns_populated_judge_result() -> None:
    llm_json = json.dumps({
        "correctness": 0.9,
        "completeness": 0.8,
        "hallucination": False,
        "format_compliant": True,
        "citation_accuracy": 0.7,
        "reasoning": "基本对，少量遗漏",
    })
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text=llm_json, stop_reason="end_turn")]
    )
    judge = Judge(llm_provider=provider, pass_threshold=0.6)

    result = await judge.evaluate(
        question="Q?",
        actual_answer="A",
        expected_answer="E",
        reference_context=["ctx"],
    )

    assert isinstance(result, JudgeResult)
    # composite = 0.9*40 + 0.8*25 + 10 + 5 + 0.7*20 = 36+20+10+5+14 = 85 / 100 = 0.85
    assert result.score == 0.85
    assert result.reasoning == "基本对，少量遗漏"
    assert result.passed is True  # 0.85 >= 0.6


# 功能：验证 pass_threshold 决定 passed 字段
# 设计：构造低分响应，调高阈值 → passed=False
async def test_evaluate_passed_follows_threshold() -> None:
    llm_json = json.dumps({
        "correctness": 0.3,
        "completeness": 0.3,
        "hallucination": True,
        "format_compliant": False,
        "citation_accuracy": 0.0,
    })
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text=llm_json, stop_reason="end_turn")]
    )
    judge = Judge(llm_provider=provider, pass_threshold=0.5)

    result = await judge.evaluate(
        question="Q?",
        actual_answer="A",
        expected_answer="E",
        reference_context=[],
    )
    # composite = 0.3*40 + 0.3*25 + 0 + 0 + 0 = 19.5 / 100 = 0.195
    assert result.score < 0.2
    assert result.passed is False


# 功能：验证 LLM 返回非 JSON 时 Judge 仍能返回 JudgeResult（不抛）
# 设计：演示版容错；reasoning 字段填原始响应
async def test_evaluate_handles_non_json_llm_response() -> None:
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="LLM 返回了一段自然语言而不是 JSON")]
    )
    judge = Judge(llm_provider=provider)

    result = await judge.evaluate(
        question="Q?",
        actual_answer="A",
        expected_answer="E",
        reference_context=[],
    )
    # score=0（无字段），passed=False
    assert result.score == 0.0
    assert result.passed is False
    # raw 字段保留 LLM 原文便于调试
    assert "LLM 返回了" in result.raw.get("_raw", "")
