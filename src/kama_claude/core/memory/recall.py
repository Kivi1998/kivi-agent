from __future__ import annotations

from kama_claude.core.memory.store import MemoryStore


# 把长期记忆列表渲染成可注入 system prompt 的文本；无记忆时返回空字符串
def build_memory_prompt(store: MemoryStore, max_entries: int = 10) -> str:
    entries = store.list_all()[:max_entries]
    if not entries:
        return ""
    lines = [f"- [{e.type}] {e.description}: {e.body}" for e in entries]
    return "\n".join(lines)
