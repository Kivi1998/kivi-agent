"""Gateway 事件 replay 缓冲：缓存最近 N 条事件，支持重连重传（agent: package-web-gateway-v3）。

设计要点：
- 客户端 WS 断线重连时携带 `?since=<ts>` query，gateway 用 since() 拉取 ts 之后的漏掉事件
- 缓存按 session_id 分桶（dict 嵌套 list）；每桶上限 100 条（FIFO，超过则丢最早）
- push 是同步 O(1) 操作（append + 长度裁剪），suitable 在 event_bridge 路径上调用
- since() 返回 ts 之后的事件（按时间戳字符串字典序比较；ISO 8601 字符串可直接字典序比较）
- 不持久化（重启清空）；不限制 session_id 数量（内存中按需分桶）
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# 事件缓冲默认上限（v1 §5.2.1 / Web Chat 计划 §三 WT-E1：100 条最近事件）
DEFAULT_MAX_SIZE: int = 100


# 构造固定大小的事件缓存，支持按 session 分桶 + 时间戳重传
class EventReplayBuffer:
    """事件缓存 + 重传（agent: package-web-gateway-v3）。"""

    # 初始化：max_size 控制每个 session 桶的事件上限
    def __init__(self, max_size: int = DEFAULT_MAX_SIZE) -> None:
        if max_size <= 0:
            raise ValueError(f"max_size must be > 0, got {max_size}")
        self._max_size = max_size
        # session_id -> deque 缓存
        self._buffers: dict[str, deque[dict[str, Any]]] = {}

    # 当前每个 session 桶的上限（只读）
    @property
    def max_size(self) -> int:
        return self._max_size

    # 推一条事件进 session 桶；超长时丢最早（FIFO）
    def push(self, session_id: str, event: dict[str, Any]) -> None:
        if not session_id:
            return  # 防御：没有 session_id 的事件不入桶
        bucket = self._buffers.get(session_id)
        if bucket is None:
            bucket = deque(maxlen=self._max_size)
            self._buffers[session_id] = bucket
        bucket.append(event)

    # 返回 session 桶中 ts > since_ts 的事件列表（按时间戳字典序）
    def since(self, session_id: str, since_ts: str) -> list[dict[str, Any]]:
        bucket = self._buffers.get(session_id)
        if bucket is None:
            return []
        # ISO 8601 字符串可直接字典序比较；since_ts 为空时返回全部
        if not since_ts:
            return list(bucket)
        # 逐个比较事件 ts 字段（v1 §5.2.1 事件都带 ts）
        result: list[dict[str, Any]] = []
        for ev in bucket:
            ev_ts = ev.get("ts", "")
            if isinstance(ev_ts, str) and ev_ts > since_ts:
                result.append(ev)
        return result

    # 清空指定 session 桶（session 关闭时调用，释放内存）
    def clear(self, session_id: str) -> None:
        self._buffers.pop(session_id, None)

    # 清空全部缓存
    def clear_all(self) -> None:
        self._buffers.clear()

    # 返回 session 桶的当前长度
    def __len__(self) -> int:
        return sum(len(b) for b in self._buffers.values())

    # 返回所有 session 桶的 session_id 列表
    def sessions(self) -> list[str]:
        return list(self._buffers.keys())


__all__ = ["EventReplayBuffer", "DEFAULT_MAX_SIZE"]
