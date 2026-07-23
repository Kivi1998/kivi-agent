"""记忆审计日志器（Wave 6.1 J2 增强）。"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from kivi_agent.core.memory.backend import MemoryAuditEvent


# 把目标路径解析后判断是否在 base_dir 之下，防止 path traversal。
def _safe_under(base_dir: Path, target: Path) -> Path:
    base = base_dir.resolve()
    resolved = target.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError(f"unsafe path traversal: {target}") from None
    return resolved


class MemoryAuditLogger:
    """审计事件 JSONL 落盘 + 查询 API。"""

    # path 必须是 .jsonl 文件；落盘前会创建父目录。
    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        """审计日志文件路径。"""
        return self._path

    # 追加一条审计事件到 JSONL 文件，线程安全。
    def append(self, event: MemoryAuditEvent) -> None:
        line = json.dumps(asdict(event), ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    # 异步包装：与 plan 中"audit(event)" 异步签名一致。
    async def record(self, event: MemoryAuditEvent) -> None:
        self.append(event)

    # 按 memory_id / since 过滤查询审计事件，按 ts 升序。
    # since 接受 ISO 8601 字符串前缀（e.g. "2026-01-01" 匹配所有 2026-01-01 开头的 ts）。
    def query(
        self,
        memory_id: str | None = None,
        since: str | None = None,
    ) -> list[MemoryAuditEvent]:
        if not self._path.exists():
            return []
        results: list[MemoryAuditEvent] = []
        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if memory_id is not None and data.get("memory_id") != memory_id:
                    continue
                if since is not None and not str(data.get("ts", "")).startswith(since):
                    continue
                results.append(MemoryAuditEvent(
                    memory_id=data["memory_id"],
                    event_type=data["event_type"],
                    ts=data["ts"],
                    actor=data["actor"],
                ))
        # 按 ts 升序
        results.sort(key=lambda e: e.ts)
        return results

    # 按时间窗口便捷查询：从 start 到 end（含）之间的事件。
    def query_range(
        self,
        start: str,
        end: str,
        memory_id: str | None = None,
    ) -> list[MemoryAuditEvent]:
        all_events = self.query(memory_id=memory_id)
        return [e for e in all_events if start <= e.ts <= end]

    # 便捷构造器：生成 create 事件并落盘。
    def log_create(self, memory_id: str, actor: str = "system:audit") -> None:
        self.append(MemoryAuditEvent(
            memory_id=memory_id,
            event_type="create",
            ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            actor=actor,
        ))


def _default_path() -> Path:
    """默认审计日志路径：~/.kivi/memory/audit.jsonl。"""
    root = Path(os.path.expanduser("~/.kivi/memory"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "audit.jsonl"


# 把任意目标 path 限定在 base_dir 之下（path traversal 防护）。
def safe_path(base_dir: Path, target: Path) -> Path:
    """校验 target 是否在 base_dir 之下；越界抛 ValueError。"""
    return _safe_under(base_dir, target)
