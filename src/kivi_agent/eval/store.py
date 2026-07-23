"""EvalResult 持久化（agent: package-eval-dataset-v51）。

按 JSONL 追加写，结果文件默认 `~/.kama/eval/results.jsonl`。
- 不依赖 Pydantic：传入对象 duck-typed on `.model_dump_json()` 即可
- 读出为 `dict[str, Any]`，调用方可按需 `EvalResult(**r)` 还原
- 路径遍历保护：拒绝包含 `..` 的 path / run_id
"""

# src/kivi_agent/eval/store.py（agent: package-dashboard-api-v51）

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol


class _Dumpable(Protocol):
    """任意可序列化为 JSON 的对象（duck-typed on Pydantic model_dump_json）。"""

    def model_dump_json(self) -> str: ...


class EvalResultStore:
    """EvalResult 持久化（agent: package-eval-dataset-v51）。"""

    #: 默认结果文件路径
    DEFAULT_PATH: Path = Path("~/.kama/eval/results.jsonl").expanduser()

    def __init__(self, path: Path | None = None) -> None:
        """构造并确保目录存在（agent: package-eval-dataset-v51）。"""
        self._path = path or self.DEFAULT_PATH
        # 路径遍历保护：拒绝 `..` 段（防止越权写到上层目录）
        if ".." in self._path.parts:
            raise ValueError(f"invalid store path: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        """当前 store 路径（agent: package-eval-dataset-v51）。"""
        return self._path

    def save(self, result: _Dumpable) -> None:
        """追加写一条 EvalResult 到 JSONL（agent: package-eval-dataset-v51）。"""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

    def save_batch(self, results: list[_Dumpable]) -> None:
        """批量追加写（agent: package-eval-dataset-v51）。"""
        for r in results:
            self.save(r)

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """列出 run 摘要（agent: package-eval-dataset-v51）。

        按 `started_at` 倒序，去重 run_id；返回 `[run_id, started_at, case_count, success_count]`。
        """
        runs: dict[str, dict[str, Any]] = {}
        for r in self.iter_all():
            rid = r.get("run_id")
            if not rid:
                continue
            if rid not in runs:
                runs[rid] = {
                    "run_id": rid,
                    "started_at": r.get("started_at"),
                    "case_count": 0,
                    "success_count": 0,
                }
            runs[rid]["case_count"] += 1
            if r.get("success"):
                runs[rid]["success_count"] += 1
        run_list = list(runs.values())
        run_list.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return run_list[offset:offset + limit]

    def get_run(self, run_id: str) -> list[dict[str, Any]]:
        """取单 run 全部 case（agent: package-eval-dataset-v51）。

        返回 list[dict]（不构造 EvalResult 对象，避免依赖 WT-G1 的 result 模块）。
        """
        if ".." in run_id:
            raise ValueError(f"invalid run_id: {run_id}")
        results: list[dict[str, Any]] = []
        for r in self.iter_all():
            if r.get("run_id") == run_id:
                results.append(r)
        return results

    def iter_all(self) -> Iterator[dict[str, Any]]:
        """迭代所有 EvalResult dict（agent: package-eval-dataset-v51）。

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


__all__ = ["EvalResultStore"]
