from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# 超过这个大小不计算 sha256（避免大文件每次读都哈希一遍 O(n)）；
# 仅用 mtime + size 检测，对超大文件足够（误报概率极低）
_SHA256_SIZE_LIMIT = 1 * 1024 * 1024  # 1 MB


@dataclass
class FileState:
    path: str
    mtime: float  # POSIX timestamp（path.stat().st_mtime）
    size: int
    sha256: str | None  # None 表示文件过大未计算


# 进程内文件状态缓存：read_file 写、edit_file 读，检测"读后改"过期情况。
# 不做持久化（每个 run / 每次启动重建），不做并发控制（单 event loop 串行调用）。
class FileStateCache:
    def __init__(self) -> None:
        # path（字符串，绝对路径）→ 最近一次 record 时的状态
        self._states: dict[str, FileState] = {}

    # 规范化 path 为绝对字符串键，避免相对/绝对混用导致同一文件被记两次
    @staticmethod
    def _key(path: Path) -> str:
        return str(path.resolve())

    # 读取 path 当前状态并存入缓存；文件不存在时记一个 size=0 的"墓碑"状态
    def record(self, path: Path) -> FileState:
        key = self._key(path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            state = FileState(path=key, mtime=0.0, size=0, sha256=None)
            self._states[key] = state
            return state

        sha: str | None = None
        if stat.st_size <= _SHA256_SIZE_LIMIT:
            sha = hashlib.sha256(path.read_bytes()).hexdigest()

        state = FileState(path=key, mtime=stat.st_mtime, size=stat.st_size, sha256=sha)
        self._states[key] = state
        return state

    # 是否曾记录过这个 path（has 是 is_stale 反向查询的前置检查）
    def has(self, path: Path) -> bool:
        return self._key(path) in self._states

    # 检测 path 当前状态与缓存中是否一致；
    # 未记录过返回 False（视为新鲜，避免无前置 read 时误报）
    def is_stale(self, path: Path) -> bool:
        key = self._key(path)
        recorded = self._states.get(key)
        if recorded is None:
            return False
        try:
            current = path.stat()
        except FileNotFoundError:
            return recorded.size != 0  # 之前有现在没了 → 过期

        if current.st_size != recorded.size:
            return True
        # mtime 精确到秒就够用——同秒内写两次的概率极低
        if current.st_mtime != recorded.mtime:
            return True
        # mtime + size 一致但内容确实被改过的极端情况（秒内覆写），用 sha256 再校一次
        if recorded.sha256 is not None and recorded.size <= _SHA256_SIZE_LIMIT:
            current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if current_sha != recorded.sha256:
                return True
        return False

    # 从缓存中删除 path（read_file 失败/显式重读时调用）
    def invalidate(self, path: Path) -> None:
        self._states.pop(self._key(path), None)
