"""CodingResult 持久化（agent: package-dashboard-api-v52）。

按 JSONL 追加写，结果文件默认 `~/.kama/eval/coding.jsonl`。
- 模式与 `EvalResultStore` 完全对齐（追加写 / 读 dict / 路径遍历保护）
- 不依赖 Pydantic：传入对象 duck-typed on `.model_dump_json()` 即可
- 读出为 `dict[str, Any]`，调用方可按需 `CodingEvalResult(**r)` 还原（H2 模块）
- 路径遍历保护：拒绝包含 `..` 的 path / run_id
"""

# src/kivi_agent/eval/coding_store.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol


class _Dumpable(Protocol):
    """任意可序列化为 JSON 的对象（duck-typed on Pydantic model_dump_json）。"""

    def model_dump_json(self) -> str: ...


class CodingResultStore:
    """CodingResult 持久化（agent: package-dashboard-api-v52）。"""

    #: 默认结果文件路径
    DEFAULT_PATH: Path = Path("~/.kama/eval/coding.jsonl").expanduser()

    def __init__(self, path: Path | None = None) -> None:
        """构造并确保目录存在（agent: package-dashboard-api-v52）。"""
        self._path = path or self.DEFAULT_PATH
        # 路径遍历保护：拒绝 `..` 段（防止越权写到上层目录）
        if ".." in self._path.parts:
            raise ValueError(f"invalid store path: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """当前 store 路径（agent: package-dashboard-api-v52）。"""
        return self._path

    def save(self, result: _Dumpable) -> None:
        """追加写一条 CodingResult 到 JSONL（agent: package-dashboard-api-v52）。"""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

    def save_batch(self, results: list[_Dumpable]) -> None:
        """批量追加写（agent: package-dashboard-api-v52）。"""
        for r in results:
            self.save(r)

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """列出 coding run 摘要（agent: package-dashboard-api-v52）。

        按 `started_at` 倒序，去重 run_id；返回 `[run_id, task, iterations, completed]`。
        """
        runs: dict[str, dict[str, Any]] = {}
        for r in self.iter_all():
            rid = r.get("run_id")
            if not rid:
                continue
            if rid not in runs:
                runs[rid] = {
                    "run_id": rid,
                    "task": r.get("task", ""),
                    "started_at": r.get("started_at"),
                    "iterations": r.get("iterations", 0) or r.get("iteration_count", 0),
                    "completed": bool(r.get("completed", r.get("success", False))),
                }
            # 同 run 多行时（demo 反复跑），更新为最新
            if r.get("started_at"):
                if not runs[rid]["started_at"] or r["started_at"] > runs[rid]["started_at"]:
                    runs[rid]["started_at"] = r["started_at"]
                    runs[rid]["iterations"] = (
                        r.get("iterations", 0) or r.get("iteration_count", 0)
                    )
                    runs[rid]["completed"] = bool(
                        r.get("completed", r.get("success", False))
                    )
        run_list = list(runs.values())
        run_list.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return run_list[offset:offset + limit]

    def get_run(self, run_id: str) -> list[dict[str, Any]]:
        """取单 run 全部行（agent: package-dashboard-api-v52）。

        返回 list[dict]（不构造 CodingEvalResult 对象，避免依赖 H2 的 models 模块）。
        """
        if ".." in run_id:
            raise ValueError(f"invalid run_id: {run_id}")
        results: list[dict[str, Any]] = []
        for r in self.iter_all():
            if r.get("run_id") == run_id:
                results.append(r)
        return results

    def iter_all(self) -> Iterator[dict[str, Any]]:
        """迭代所有 CodingResult dict（agent: package-dashboard-api-v52）。

        解析失败的行被静默跳过（避免单条坏数据污染整个读取）。
        """
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


__all__ = ["CodingResultStore"]
