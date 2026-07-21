from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from kama_claude.core.events.bus import EventBus
from kama_claude.core.memory.store import MemoryEntry, MemoryStore

if TYPE_CHECKING:
    from kama_claude.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """\
Review this conversation and decide if there is anything worth remembering long-term \
(a durable user preference, a project fact, a piece of feedback, or a useful reference).
If there is, respond with EXACTLY this format (one entry):

MEMORY_NAME: <short-kebab-case-slug>
MEMORY_TYPE: <user|feedback|project|reference>
MEMORY_DESC: <one-line description>
MEMORY_BODY: <the durable fact itself>
---END---

If there is nothing worth remembering, respond with exactly: NOTHING

Conversation:
{conversation}
"""

_FIELD_RE = {
    "name": re.compile(r"MEMORY_NAME:\s*(.+)"),
    "type": re.compile(r"MEMORY_TYPE:\s*(.+)"),
    "description": re.compile(r"MEMORY_DESC:\s*(.+)"),
    "body": re.compile(r"MEMORY_BODY:\s*(.+)"),
}


# 用 LLM 从一轮对话消息中抽取值得长期记住的内容，解析后写入 MemoryStore；失败静默返回 0，不影响主流程
async def extract_memories(
    messages: list[dict[str, object]],
    provider: LLMProvider,
    store: MemoryStore,
) -> int:
    conversation = "\n".join(
        f"[{m.get('role')}] {m.get('content')}" for m in messages if isinstance(m.get("content"), str)
    )
    if not conversation.strip():
        return 0

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(conversation=conversation)}],
            tool_schemas=[],
            bus=EventBus(),
            run_id="memory-extract",
        )
    except Exception:
        logger.exception("memory extractor: LLM call failed")
        return 0

    text = response.text.strip()
    if text == "NOTHING" or not text:
        return 0

    fields: dict[str, str] = {}
    for key, pattern in _FIELD_RE.items():
        match = pattern.search(text)
        if match:
            fields[key] = match.group(1).strip()

    if not all(k in fields for k in ("name", "type", "description", "body")):
        logger.warning("memory extractor: LLM response did not match expected format")
        return 0

    store.write(MemoryEntry(
        name=fields["name"], type=fields["type"],
        description=fields["description"], body=fields["body"],
    ))
    return 1
