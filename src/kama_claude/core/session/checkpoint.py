from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckpointData:
    run_id: str
    step: int
    status: str  # "running" | "success" | "failed"
    message_count: int
    ts: str


class CheckpointStore:
    # 初始化检查点存储，复用 session 根目录（和 SessionStore 指向同一目录树）
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    # 返回指定 run 的检查点文件路径
    def _path(self, sid: str, run_id: str) -> Path:
        return self._root / sid / "runs" / run_id / "checkpoint.json"

    # 保存检查点，覆盖式写入（每个 run 只保留最新一份）
    def save(self, sid: str, run_id: str, data: CheckpointData) -> None:
        path = self._path(sid, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(data), ensure_ascii=False, indent=2), encoding="utf-8")

    # 加载检查点；不存在时返回 None
    def load(self, sid: str, run_id: str) -> CheckpointData | None:
        path = self._path(sid, run_id)
        if not path.exists():
            return None
        return CheckpointData(**json.loads(path.read_text(encoding="utf-8")))
