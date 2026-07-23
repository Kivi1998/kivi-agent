"""TeamResult 持久化（agent: package-dashboard-api-v52）。

按 JSONL 追加写，结果文件默认 `~/.kama/eval/teams.jsonl`。
- 模式与 `EvalResultStore` 完全对齐（追加写 / 读 dict / 路径遍历保护）
- 不依赖 Pydantic：传入对象 duck-typed on `.model_dump_json()` 即可
- 读出为 `dict[str, Any]`，调用方可按需 `TeamEvalResult(**r)` 还原（H1 模块）
- 路径遍历保护：拒绝包含 `..` 的 path / team_id
"""

# src/kivi_agent/eval/team_store.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol


class _Dumpable(Protocol):
    """任意可序列化为 JSON 的对象（duck-typed on Pydantic model_dump_json）。"""

    def model_dump_json(self) -> str: ...


class TeamResultStore:
    """TeamResult 持久化（agent: package-dashboard-api-v52）。"""

    #: 默认结果文件路径
    DEFAULT_PATH: Path = Path("~/.kama/eval/teams.jsonl").expanduser()

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
        """追加写一条 TeamResult 到 JSONL（agent: package-dashboard-api-v52）。"""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

    def save_batch(self, results: list[_Dumpable]) -> None:
        """批量追加写（agent: package-dashboard-api-v52）。"""
        for r in results:
            self.save(r)

    def list_teams(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """列出 team 摘要（agent: package-dashboard-api-v52）。

        按 `started_at` 倒序，去重 team_id；返回 `[team_id, goal, member_count, success]`。
        """
        teams: dict[str, dict[str, Any]] = {}
        for r in self.iter_all():
            tid = r.get("team_id")
            if not tid:
                continue
            if tid not in teams:
                teams[tid] = {
                    "team_id": tid,
                    "goal": r.get("goal", ""),
                    "started_at": r.get("started_at"),
                    "member_count": r.get("member_count", 0) or len(r.get("member_specs", [])),
                    "success": bool(r.get("success", False)),
                }
            # 同 team 多行时（demo 反复跑），更新为最新
            if r.get("started_at"):
                if not teams[tid]["started_at"] or r["started_at"] > teams[tid]["started_at"]:
                    teams[tid]["started_at"] = r["started_at"]
                    teams[tid]["success"] = bool(r.get("success", False))
        team_list = list(teams.values())
        team_list.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return team_list[offset:offset + limit]

    def get_team(self, team_id: str) -> list[dict[str, Any]]:
        """取单 team 全部行（agent: package-dashboard-api-v52）。

        返回 list[dict]（不构造 TeamEvalResult 对象，避免依赖 H1 的 models 模块）。
        """
        if ".." in team_id:
            raise ValueError(f"invalid team_id: {team_id}")
        results: list[dict[str, Any]] = []
        for r in self.iter_all():
            if r.get("team_id") == team_id:
                results.append(r)
        return results

    def iter_all(self) -> Iterator[dict[str, Any]]:
        """迭代所有 TeamResult dict（agent: package-dashboard-api-v52）。

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


__all__ = ["TeamResultStore"]
