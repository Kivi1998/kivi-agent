from __future__ import annotations

import json

from kivi_agent.core.llm.types import ToolCallBlock


class StreamAccumulator:
    # 初始化空的文本片段列表和按 index 分组的工具调用缓冲区
    def __init__(self) -> None:
        self._text_parts: list[str] = []
        self._tool_call_buffers: dict[int, dict[str, str]] = {}

    # 追加一段文本增量
    def add_content_delta(self, text: str) -> None:
        self._text_parts.append(text)

    # 按 index 累加一次工具调用增量；id/name 只在非空时覆盖，arguments 始终追加
    def add_tool_call_delta(self, index: int, id: str, name: str, arguments: str) -> None:
        buf = self._tool_call_buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if id:
            buf["id"] = id
        if name:
            buf["name"] = name
        if arguments:
            buf["arguments"] += arguments

    # 聚合所有增量，返回完整文本和已解析的 ToolCallBlock 列表
    def finalize(self) -> tuple[str, list[ToolCallBlock]]:
        text = "".join(self._text_parts)
        tool_calls = [
            ToolCallBlock(
                id=buf["id"], name=buf["name"], input=json.loads(buf["arguments"] or "{}")
            )
            for buf in self._tool_call_buffers.values()
        ]
        return text, tool_calls
