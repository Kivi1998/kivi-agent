from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

TOOL_RESULT_LIMIT = 8_000
TOOL_RESULT_KEEP = 4_000


# 对消息列表中超长的 tool_result 内容做内存截断，返回处理后的新列表
def truncate_tool_results(
    messages: list[dict[str, Any]],
    limit: int = TOOL_RESULT_LIMIT,
    keep: int = TOOL_RESULT_KEEP,
) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("role") != "user":
            result.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        new_blocks = []
        for block in content:
            if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                text = block["content"]
                if len(text) > limit:
                    omitted = len(text) - keep
                    block = dict(block)
                    block["content"] = (
                        text[:keep]
                        + f"\n[... {omitted} chars omitted. Full output in run events.]"
                    )
            new_blocks.append(block)
        result.append({**msg, "content": new_blocks})
    return result


# 对超长 tool_result 内容落盘保存完整版本，对话里替换为引用占位符；未超限内容原样保留
def persist_and_truncate_tool_results(
    messages: list[dict[str, Any]],
    session_dir: Path,
    limit: int = TOOL_RESULT_LIMIT,
) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("role") != "user":
            result.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        new_blocks = []
        for block in content:
            if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                text = block["content"]
                if len(text) > limit:
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                    out_dir = session_dir / "tool_outputs"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{digest}.txt"
                    out_path.write_text(text, encoding="utf-8")
                    block = dict(block)
                    block["content"] = (
                        f"[persisted: tool_outputs/{digest}.txt, "
                        f"{len(text)} chars omitted from context — read the file if full content is needed]"
                    )
            new_blocks.append(block)
        result.append({**msg, "content": new_blocks})
    return result
