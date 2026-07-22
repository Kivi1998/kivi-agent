from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class FileSnapshot:
    version: str  # 时间戳形式的唯一 id，如 "20260721_120304_123456"
    path: str  # 原始文件相对路径
    ts: str  # ISO 8601
    size: int
    content: bytes


# 文件历史快照：每次调用 snapshot() 把当前内容复制到 root 目录下
# <sanitized_path>/<version>.bak，按时间戳排序；get_version 按 version id 取回原内容。
# 路径存储用相对路径做子目录（避免文件名冲突），特殊字符替换为下划线。
class FileHistory:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    # 把原始路径净化成可作为目录名的字符串（"src/a.py" → "src_a.py"）
    @staticmethod
    def _sanitize(path: Path) -> str:
        s = str(path).replace("\\", "/")
        s = re.sub(r"[^A-Za-z0-9_./-]", "_", s)
        s = s.replace("/", "_")
        return s or "root"

    # 当前时间戳作为 version id（微秒精度保证同秒内也不冲突）
    @staticmethod
    def _now_version() -> tuple[str, str]:
        now = datetime.now(UTC)
        version = now.strftime("%Y%m%d_%H%M%S_%f")
        iso = now.isoformat()
        return version, iso

    # 快照目录：<root>/<sanitized_path>/
    def _dir(self, path: Path) -> Path:
        d = self._root / self._sanitize(path)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # 快照文件路径：<root>/<sanitized_path>/<version>.bak
    def _file(self, path: Path, version: str) -> Path:
        return self._dir(path) / f"{version}.bak"

    # 把 path 当前内容写到 root 下的一个 .bak 文件，返回 FileSnapshot
    def snapshot(self, path: Path) -> FileSnapshot:
        version, iso = self._now_version()
        content = path.read_bytes()
        target = self._file(path, version)
        target.write_bytes(content)
        return FileSnapshot(
            version=version,
            path=str(path),
            ts=iso,
            size=len(content),
            content=content,
        )

    # 列出 path 这个文件的所有快照版本，按 version id（时间戳）升序
    def list_versions(self, path: Path) -> list[FileSnapshot]:
        d = self._dir(path)
        results: list[FileSnapshot] = []
        for bak in sorted(d.glob("*.bak")):
            version = bak.stem
            content = bak.read_bytes()
            results.append(
                FileSnapshot(
                    version=version,
                    path=str(path),
                    ts="",  # 列出时不再回查 ISO 字符串
                    size=len(content),
                    content=content,
                )
            )
        return results

    # 按 version id 取回指定快照；不存在抛 FileNotFoundError
    def get_version(self, path: Path, version: str) -> FileSnapshot:
        bak = self._file(path, version)
        if not bak.exists():
            raise FileNotFoundError(f"no snapshot version '{version}' for {path}")
        content = bak.read_bytes()
        return FileSnapshot(
            version=version,
            path=str(path),
            ts="",
            size=len(content),
            content=content,
        )

    # 返回快照文件的磁盘路径（rewind 时直接用，避免在内存里多读一遍）
    def get_path(self, path: Path, version: str) -> Path:
        return self._file(path, version)

    # 把文件内容还原到 version 指定的快照；文件不存在时抛 FileNotFoundError，
    # version 不存在时抛 FileNotFoundError；用原子写入避免写到一半损坏
    def rewind(self, path: Path, version: str) -> None:
        snap = self.get_version(path, version)  # raises FileNotFoundError if missing
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(snap.content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
