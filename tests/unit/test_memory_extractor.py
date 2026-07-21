from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from kama_claude.core.memory.extractor import extract_memories
from kama_claude.core.memory.store import MemoryStore


# 功能：验证 LLM 返回结构化的 MEMORY 块时，能正确解析并写入 MemoryStore
# 设计：mock provider 返回一个符合约定格式的文本块，断言 extract_memories 返回写入条数为 1，
#      且 store 里确实出现了对应内容
async def test_extract_memories_parses_and_writes(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=MagicMock(
        text=(
            "MEMORY_NAME: prefer-tests\n"
            "MEMORY_TYPE: feedback\n"
            "MEMORY_DESC: 用户希望改动都先写测试\n"
            "MEMORY_BODY: 任何代码修改前先写失败测试再实现\n"
            "---END---"
        ),
    ))
    count = await extract_memories(
        [{"role": "user", "content": "以后改代码都先写测试"}], fake_provider, store,
    )
    assert count == 1
    entries = store.list_all()
    assert entries[0].name == "prefer-tests"
    assert entries[0].type == "feedback"


# 功能：验证 LLM 调用失败时 extract_memories 吞掉异常返回 0，不向上抛出
# 设计：mock provider 的 chat 方法直接抛异常，断言函数正常返回 0 而不是让异常传播——
#      抽取是后台辅助功能，绝不能因为一次 LLM 调用失败拖垮调用方
async def test_extract_memories_swallows_llm_failure(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(side_effect=RuntimeError("network error"))
    count = await extract_memories([{"role": "user", "content": "x"}], fake_provider, store)
    assert count == 0


# 功能：验证 LLM 返回 NOTHING 时不写入记忆、返回 0
# 设计：mock provider 返回 "NOTHING"，断言 store 为空且返回 0
async def test_extract_memories_handles_nothing_response(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=MagicMock(text="NOTHING"))
    count = await extract_memories([{"role": "user", "content": "hi"}], fake_provider, store)
    assert count == 0
    assert store.list_all() == []


# 功能：验证 LLM 返回非 NOTHING 但缺字段时不写入、不抛异常
# 设计：mock provider 返回缺少 MEMORY_BODY 的块，断言返回 0、store 仍空
async def test_extract_memories_skips_malformed_response(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(return_value=MagicMock(
        text="MEMORY_NAME: foo\nMEMORY_TYPE: project\nMEMORY_DESC: d\n---END---"
    ))
    count = await extract_memories([{"role": "user", "content": "x"}], fake_provider, store)
    assert count == 0
    assert store.list_all() == []
