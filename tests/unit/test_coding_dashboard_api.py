"""Coding Dashboard API 单元测试（WT-H3 / agent: package-dashboard-api-v52）。

测试目标：
1. 5 个端点的请求/响应 schema
2. CodingResultStore JSONL 持久化（追加写 / 读取 / list_runs 分组）
3. 路径遍历保护（`..` in run_id → 400）
4. metrics 端点用 mock 注入（H2 模块当前不可用，测 handler 行为）
5. _ensure_safe_run_id / summary / 各种 200 / 404 场景

设计要点：
- 用 `coding_dashboard.reset_coding_store_for_test()` 隔离单例 + tmp_path 注入 store
- 用 `Pydantic BaseModel` 模拟 CodingResult
- 不依赖 H2 (CodingEvalResult/CodingAgent/metrics.coding) 的实现
"""

# tests/unit/test_coding_dashboard_api.py（agent: package-dashboard-api-v52）

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import coding_dashboard as coding_dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- Mock 数据模型 ---------------------------------------------------------


class _MockCodingResult(BaseModel):
    """Mock CodingResult（H2 CodingEvalResult 的最小替代）。"""

    run_id: str
    task: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    completed: bool = False
    success: bool = False
    iterations: int = 0
    iteration_count: int = 0
    patches: list[dict[str, Any]] = []
    test_runs: list[dict[str, Any]] = []


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v52）。"""
    return tmp_path / "coding.jsonl"


@pytest.fixture
def patch_store(store_path: Path):
    """注入临时 CodingResultStore + 清理单例（agent: package-dashboard-api-v52）。"""
    from kivi_agent.eval.coding_store import CodingResultStore

    store = CodingResultStore(store_path)
    coding_dashboard_mod._coding_store = store
    yield store
    coding_dashboard_mod._coding_store = None


class _FakeRuntime:
    """FastAPI create_app 注入的 fake runtime。"""

    async def start_session(self, *args: Any, **kwargs: Any) -> Any:
        from kivi_agent.core.gateway.runtime import SessionInfo

        return SessionInfo(
            session_id="x",
            user_id="u",
            goal="g",
            created_at="2026-01-01T00:00:00Z",
            status="active",
            run_id=None,
        )

    async def cancel_session(self, *args: Any, **kwargs: Any) -> bool:
        return True

    async def list_sessions(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def get_session(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def send_command(self, *args: Any, **kwargs: Any) -> Any:
        return {}

    def subscribe_events(self, *args: Any, **kwargs: Any) -> Any:
        async def _gen() -> Any:
            if False:
                yield  # type: ignore[unreachable]

        return _gen()


@pytest.fixture
def client(patch_store: Any) -> TestClient:
    """FastAPI TestClient + coding store 注入（agent: package-dashboard-api-v52）。"""
    app = create_app(runtime=_FakeRuntime())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


# ---- 工具函数 --------------------------------------------------------------


def _make_result(**kwargs: Any) -> _MockCodingResult:
    """构造 MockCodingResult（agent: package-dashboard-api-v52）。"""
    defaults: dict[str, Any] = {
        "run_id": "r-1",
        "task": "Write add(a,b)",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "completed": True,
        "iterations": 2,
    }
    defaults.update(kwargs)
    return _MockCodingResult(**defaults)


# ---- /summary 端点测试 -----------------------------------------------------


# 功能：summary 在无数据时返回全 0 占位
# 设计：fresh store → run_count=0, completion_rate=0.0, avg_iterations=0.0
def test_summary_empty(client: TestClient) -> None:
    resp = client.get("/api/coding/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "run_count": 0,
        "completion_rate": 0.0,
        "avg_iterations": 0.0,
    }


# 功能：summary 在有 3 runs 时计算 completion_rate / avg_iterations
# 设计：3 条 coding result 写入 store（2 完成 / 1 未完成），断言比例 + 平均迭代
def test_summary_with_runs(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result(run_id="r-1", completed=True, iterations=2))
    patch_store.save(_make_result(run_id="r-2", completed=True, iterations=4))
    patch_store.save(_make_result(run_id="r-3", completed=False, iterations=3))

    resp = client.get("/api/coding/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_count"] == 3
    assert body["completion_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert body["avg_iterations"] == pytest.approx(3.0)


# ---- /runs 端点测试 --------------------------------------------------------


# 功能：runs 端点按 limit/offset 分页返回 run 摘要
# 设计：3 个 run 各 1 case，验证 list_runs 按 started_at 倒序
def test_list_runs_default(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result(run_id="r-1", started_at="2026-01-01T00:00:00"))
    patch_store.save(_make_result(run_id="r-2", started_at="2026-01-03T00:00:00"))
    patch_store.save(_make_result(run_id="r-3", started_at="2026-01-02T00:00:00"))

    resp = client.get("/api/coding/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    run_ids = [r["run_id"] for r in body["runs"]]
    assert run_ids == ["r-2", "r-3", "r-1"]


# ---- /runs/{run_id} 端点测试 -----------------------------------------------


# 功能：runs/{run_id} 不存在时返回 404
# 设计：空 store + 随机 run_id → 404 + detail 含 run_id
def test_get_run_not_found(client: TestClient) -> None:
    resp = client.get("/api/coding/runs/missing-run")
    assert resp.status_code == 404
    assert "missing-run" in resp.json()["detail"]


# 功能：runs/{run_id} 存在时返回完整 run 详情
# 设计：写入 1 run → 验证 patches / test_runs 都返回
def test_get_run_detail(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockCodingResult(
            run_id="r-detail",
            task="Write fib",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T00:00:05",
            completed=True,
            iterations=3,
            patches=[
                {"iter": 1, "file": "fib.py", "hunks_applied": 2, "hunks_proposed": 2},
            ],
            test_runs=[{"iter": 1, "passed": 3, "total": 3}],
        )
    )
    resp = client.get("/api/coding/runs/r-detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r-detail"
    assert body["iterations"] == 3
    assert len(body["patches"]) == 1
    assert body["patches"][0]["file"] == "fib.py"
    assert len(body["test_runs"]) == 1


# ---- /runs/{run_id}/patches 端点测试 ---------------------------------------


# 功能：patches 端点只返回 patches 字段
# 设计：写入 1 run 带 patches → 验证 patch_count + patches
def test_get_run_patches(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockCodingResult(
            run_id="r-p",
            patches=[
                {"iter": 1, "file": "a.py", "hunks_applied": 1, "hunks_proposed": 1},
                {"iter": 2, "file": "a.py", "hunks_applied": 1, "hunks_proposed": 1},
            ],
        )
    )
    resp = client.get("/api/coding/runs/r-p/patches")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "r-p"
    assert body["patch_count"] == 2
    assert len(body["patches"]) == 2
    assert body["patches"][0]["iter"] == 1


# 功能：patches 端点 run 不存在时返回 404
# 设计：空 store → 404
def test_get_run_patches_not_found(client: TestClient) -> None:
    resp = client.get("/api/coding/runs/missing/patches")
    assert resp.status_code == 404


# ---- /runs/{run_id}/metrics 端点测试 ---------------------------------------


# 功能：metrics 端点调用 H2 compute_coding_metrics 并返回 8 指标
# 设计：mock compute_coding_metrics + CodingEvalResult 避免依赖未合并模块
def test_get_run_metrics_8_indicators(client: TestClient, patch_store: Any) -> None:
    patch_store.save(
        _MockCodingResult(
            run_id="r-m",
            started_at="2026-01-01T00:00:00",
            finished_at="2026-01-01T00:00:05",
        )
    )

    fake_metrics = {
        "task_completion_rate": 0.8,
        "tests_passed_rate": 0.9,
        "patch_quality": 0.7,
        "iteration_count": 3,
        "time_to_first_pass": 12.5,
        "self_recovery_rate": 0.5,
        "compile_success_rate": 1.0,
        "test_growth_rate": 0.4,
    }

    # 模拟 H2 模块不存在
    fake_coding_pkg = types.ModuleType("kivi_agent.eval.coding")
    fake_coding_models = types.ModuleType("kivi_agent.eval.coding.models")
    fake_metrics_pkg = types.ModuleType("kivi_agent.eval.metrics")
    fake_metrics_coding = types.ModuleType("kivi_agent.eval.metrics.coding")

    class _FakeCodingEvalResult(BaseModel):
        run_id: str
        started_at: str | None = None
        finished_at: str | None = None
        completed: bool = False

    fake_coding_models.CodingEvalResult = _FakeCodingEvalResult  # type: ignore[attr-defined]
    fake_metrics_coding.compute_coding_metrics = lambda _r: fake_metrics  # type: ignore[attr-defined]

    with patch.dict(
        sys.modules,
        {
            "kivi_agent.eval.coding": fake_coding_pkg,
            "kivi_agent.eval.coding.models": fake_coding_models,
            "kivi_agent.eval.metrics": fake_metrics_pkg,
            "kivi_agent.eval.metrics.coding": fake_metrics_coding,
        },
    ):
        resp = client.get("/api/coding/runs/r-m/metrics")

    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {
        "task_completion_rate",
        "tests_passed_rate",
        "patch_quality",
        "iteration_count",
        "time_to_first_pass",
        "self_recovery_rate",
        "compile_success_rate",
        "test_growth_rate",
    }
    assert expected_keys.issubset(body.keys())
    assert body["task_completion_rate"] == 0.8


# 功能：metrics 端点在 H2 未合并时返回 501
# 设计：清空 sys.modules 的 coding 让 lazy import 失败 → HTTPException 501
def test_get_run_metrics_501_when_modules_missing(
    client: TestClient, patch_store: Any
) -> None:
    patch_store.save(_MockCodingResult(run_id="r-x"))

    with patch.dict(
        sys.modules,
        {
            "kivi_agent.eval.coding": None,
            "kivi_agent.eval.coding.models": None,
            "kivi_agent.eval.metrics": None,
            "kivi_agent.eval.metrics.coding": None,
        },
    ):
        resp = client.get("/api/coding/runs/r-x/metrics")

    assert resp.status_code == 501
    assert "not available" in resp.json()["detail"]


# ---- 路径遍历保护测试 -----------------------------------------------------


# 功能：run_id 含 `..` 时返回 400（路径遍历保护）
# 设计：覆盖 3 个动态路由
def test_path_traversal_run_id(client: TestClient) -> None:
    r1 = client.get("/api/coding/runs/..bad..")
    assert r1.status_code == 400
    r2 = client.get("/api/coding/runs/..r../patches")
    assert r2.status_code == 400
    r3 = client.get("/api/coding/runs/foo..bar..baz/metrics")
    assert r3.status_code == 400
    assert "invalid run_id" in r1.json()["detail"]


# ---- 单例管理测试 ---------------------------------------------------------


# 功能：reset_coding_store_for_test 后再 get_coding_store 会重建单例
# 设计：set → reset → 重新 get 返回新实例
def test_reset_coding_store_for_test() -> None:
    from kivi_agent.eval.coding_store import CodingResultStore

    custom = CodingResultStore(Path("/tmp/test_reset_coding.jsonl"))
    coding_dashboard_mod._coding_store = custom
    assert coding_dashboard_mod.get_coding_store() is custom
    coding_dashboard_mod.reset_coding_store_for_test()
    default = coding_dashboard_mod.get_coding_store()
    assert default is not custom
    coding_dashboard_mod.reset_coding_store_for_test()
