from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把一条消息以独立文件写入收件人目录；用 O_CREAT|O_EXCL 保证并发写入不互相覆盖
def write_message(mailbox_root: Path, recipient: str, sender: str, content: str) -> None:
    recipient_dir = mailbox_root / "mailbox" / recipient
    recipient_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"sender": sender, "content": content, "ts": _now()}, ensure_ascii=False)
    # 文件名含单调递增的纳秒时间戳，保证 sorted() 遍历顺序等价于写入顺序
    filename = f"{time.time_ns()}_{uuid.uuid4().hex[:8]}.json"
    path = recipient_dir / filename
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)


# 读取并清空指定收件人的所有待处理消息，按写入顺序返回
def consume_messages(mailbox_root: Path, recipient: str) -> list[dict[str, str]]:
    recipient_dir = mailbox_root / "mailbox" / recipient
    if not recipient_dir.exists():
        return []
    messages: list[dict[str, str]] = []
    for path in sorted(recipient_dir.glob("*.json")):
        try:
            messages.append(json.loads(path.read_text(encoding="utf-8")))
        finally:
            path.unlink(missing_ok=True)
    return messages
