from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_DIR_NAME = "replacements"


@dataclass
class ReplacementRecord:
    ts: str
    original_message_count: int
    original_tokens: int
    summary_text: str
    summary_tokens: int


# 把一条压缩替换记录写入 session 目录下 replacements/ 子目录，每条记录独立文件（追加式，不覆盖）
def write_replacement_record(session_dir: Path, record: ReplacementRecord) -> Path:
    replacements_dir = session_dir / _DIR_NAME
    replacements_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = replacements_dir / f"replacement_{ts_slug}.json"
    path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# 按文件名顺序（等价于时间顺序）读取该 session 下所有替换记录
def list_replacement_records(session_dir: Path) -> list[ReplacementRecord]:
    replacements_dir = session_dir / _DIR_NAME
    if not replacements_dir.exists():
        return []
    records = []
    for path in sorted(replacements_dir.glob("replacement_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        records.append(ReplacementRecord(**data))
    return records
