from __future__ import annotations

from pathlib import Path

from kama_claude.core.memory.recall import build_memory_prompt
from kama_claude.core.memory.store import MemoryEntry, MemoryStore


# 功能：验证召回文本包含每条记忆的 description 和 body
# 设计：写入两条记忆后构建召回文本，断言两条的关键信息都出现在结果字符串里
def test_build_memory_prompt_includes_all_entries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="a", type="feedback", description="偏好简洁回复", body="不要啰嗦"))
    store.write(MemoryEntry(name="b", type="project", description="部署方式", body="用 docker-compose"))
    prompt = build_memory_prompt(store)
    assert "不要啰嗦" in prompt
    assert "用 docker-compose" in prompt


# 功能：验证没有任何记忆时返回空字符串，而不是一段"没有记忆"的噪音文本
# 设计：空 store 调用，断言结果为空字符串，确保 ExecutionContext.system_prompt() 里的
#      "非空才拼接" 判断（沿用现有 global_context/session_notes 的写法）能正常跳过
def test_build_memory_prompt_empty_when_no_entries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    assert build_memory_prompt(store) == ""


# 功能：验证召回文本带 type 前缀以便 LLM 区分记忆类别
# 设计：写入两条不同 type 的记忆，断言 prompt 文本中包含 type 标记
def test_build_memory_prompt_includes_type_label(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="u", type="user", description="d", body="b1"))
    store.write(MemoryEntry(name="r", type="reference", description="d", body="b2"))
    prompt = build_memory_prompt(store)
    assert "[user]" in prompt
    assert "[reference]" in prompt
