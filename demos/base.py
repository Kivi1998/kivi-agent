"""5 演示用例基类（agent: package-demo-v7）。

# base.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 设计 `DemoBase`，统一封装 5 个 demo 的 setup / run / teardown / report：

- setup：构造 FakeLlmProvider / FakeEventBus / 临时目录，注入 mock 业务 Tool
- run：子类实现 demo 业务逻辑，输出 DemoResult（status / artifacts / summary）
- teardown：清理临时文件 + 把状态写回 stdout 汇总
- report：把 DemoResult 渲染为人类可读 1 行 + 持久化 reports/demo_*.json

使用方式：
    class Demo1Coding(DemoBase):
        name = "demo1_coding"
        async def run(self) -> DemoResult: ...
"""
from __future__ import annotations

import json
import tempfile
import time
import traceback
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar


# 当前 UTC 时间的 ISO 8601 字符串
def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# 演示用例的运行结果（agent: package-demo-v7）
@dataclass
class DemoResult:
    """单个 demo 的运行结果。"""

    name: str
    status: str  # "passed" | "failed" | "skipped"
    summary: str
    duration_seconds: float
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    started_at: str = field(default_factory=_now_iso)
    finished_at: str | None = None

    # 序列化为 dict 便于写入 reports/demo_*.json
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 5 演示用例基类（agent: package-demo-v7）
class DemoBase:
    """5 演示用例的基类：统一 setup / run / teardown / report 流程。

    子类必须实现：
        - `name` 类属性：demo 标识（同时是 reports/demo_<name>.json 的文件名）
        - `description` 类属性：1 行人类可读描述
        - `run(self) -> DemoResult` 异步方法：实际业务逻辑

    框架会自动：
        - 构造时记录开始时间 + 临时目录
        - 捕获 run() 抛出的任何异常 → status="failed"
        - 写 reports/demo_<name>.json
        - 打印 1 行汇总到 stdout（与 `scripts/run_demos.sh` 配套）
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    # reports 目录：相对工作目录；scripts/run_demos.sh 会 mkdir -p
    reports_dir: ClassVar[Path] = Path("reports")

    def __init__(self) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__} must set class attribute `name`")
        # 每个 demo 实例独占的临时目录（teardown 清理）
        self._tmpdir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(
            prefix=f"kivi-demo-{self.name}-"
        )
        self.workdir: Path = Path(self._tmpdir.name)

    # 进入 demo（teardown 钩子注册）
    def __enter__(self) -> "DemoBase":
        return self

    # 退出 demo（清理临时目录）
    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._tmpdir.cleanup()

    # async 上下文管理器：与 `async with Demo() as demo` 配合
    async def __aenter__(self) -> "DemoBase":
        return self

    # async 退出：清理临时目录
    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._tmpdir.cleanup()

    # 子类必须实现：跑 demo 业务逻辑，返回 DemoResult
    async def run(self) -> DemoResult:  # pragma: no cover - abstract
        raise NotImplementedError

    # 框架入口：捕获异常 + 计时 + 写 report
    async def execute(self) -> DemoResult:
        """执行一次完整 demo：setup → run → teardown → report。"""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        started = time.time()
        started_at = _now_iso()
        result: DemoResult | None = None
        try:
            result = await self.run()
        except Exception as exc:  # noqa: BLE001 — 演示版要兜住所有异常
            tb = traceback.format_exc()
            result = DemoResult(
                name=self.name,
                status="failed",
                summary=f"{self.description} — exception: {exc!s}",
                duration_seconds=time.time() - started,
                artifacts={},
                error=tb,
                started_at=started_at,
                finished_at=_now_iso(),
            )
        # 兜底：run 没返回结果时构造一个失败结果
        if result is None:
            result = DemoResult(
                name=self.name,
                status="failed",
                summary=f"{self.description} — run() returned None",
                duration_seconds=time.time() - started,
                artifacts={},
                error="run() returned None",
                started_at=started_at,
                finished_at=_now_iso(),
            )
        # 补齐时间戳 + 落盘
        result.finished_at = result.finished_at or _now_iso()
        result.duration_seconds = (
            result.duration_seconds if result.duration_seconds > 0 else time.time() - started
        )
        self._write_report(result)
        self._print_summary(result)
        return result

    # 写 reports/demo_<name>.json
    def _write_report(self, result: DemoResult) -> None:
        path = self.reports_dir / f"demo_{self.name}.json"
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 1 行 stdout 汇总（与 scripts/run_demos.sh 配合抓取）
    def _print_summary(self, result: DemoResult) -> None:
        flag = {"passed": "✓", "failed": "✗", "skipped": "○"}.get(result.status, "?")
        print(
            f"[{flag}] {result.name} ({result.duration_seconds:.2f}s) "
            f"{result.status.upper()}: {result.summary}",
            flush=True,
        )


# 汇总多个 DemoResult 为 1 份报告（agent: package-demo-v7）
def aggregate_reports(results: Sequence[DemoResult]) -> dict[str, Any]:
    """聚合多个 demo 结果为 1 份汇总 dict。"""
    total = len(results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "all_passed": failed == 0 and passed == total,
        "results": [r.to_dict() for r in results],
        "generated_at": _now_iso(),
    }
