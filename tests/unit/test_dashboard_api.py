"""Trace Dashboard API 单元测试（WT-G3 / agent: package-dashboard-api-v51）。

测试目标：
1. 5 个 dashboard 端点的请求/响应 schema
2. EvalResultStore JSONL 持久化（追加写 / 读取 / list_runs 分组）
3. 路径遍历保护（`..` in run_id → 400）
4. metrics 端点用 mock 注入（WT-G1/G2 模块当前不可用，测 handler 行为）

设计要点：
- 用 `dashboard.reset_eval_store_for_test()` 隔离单例 + tmp_path 注入 store
- 用 `Pydantic BaseModel` 模拟 EvalResult（`model_dump_json()` 接口一致）
- 不依赖 WT-G1 (EvalResult/EvalDataset) / WT-G2 (compute_all_metrics) 的实现
"""

# tests/unit/test_dashboard_api.py（agent: package-dashboard-api-v51）

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from kivi_agent.gateway import dashboard as dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- Mock 数据模型 ---------------------------------------------------------


class _MockEvent(BaseModel):
    """Mock 事件模型（模拟 EvalResult.events 元素）。"""

    type: str
    ts: str
    data: dict[str, Any] = {}


class _MockToolCall(BaseModel):
    """Mock 工具调用模型（模拟 EvalResult.tool_calls 元素）。"""

    name: str
    args: dict[str, Any] = {}


class _MockEvalResult(BaseModel):
    """Mock EvalResult（WT-G1 result.py 的最小替代）。

    字段名 + 类型与 `EvalResult` 对齐；测试用它构造 store / 喂给 dashboard。
    """

    case_id: str
    run_id: str
    started_at: str
    finished_at: str
    success: bool = False
    final_answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    events: list[_MockEvent] = []
    tool_calls: list[_MockToolCall] = []
    rag_sources: list[str] = []


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v51）。"""
    return tmp_path / "results.jsonl"


@pytest.fixture
def patch_store(store_path: Path):
    """注入临时 EvalResultStore + 清理单例（agent: package-dashboard-api-v51）。"""
    from kivi_agent.eval.store import EvalResultStore

    store = EvalResultStore(store_path)
    dashboard_mod._eval_store = store
    yield store
    dashboard_mod._eval_store = None


@pytest.fixture
def client(patch_store: Any) -> TestClient:
    """FastAPI TestClient + dashboard store 注入（agent: package-dashboard-api-v51）。"""
    from kivi_agent.core.gateway.runtime import SessionInfo

    class _Runtime:
        async def start_session(self, *args: Any, **kwargs: Any) -> SessionInfo:
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

        async def list_sessions(self, *args: Any, **kwargs: Any) -> list[SessionInfo]:
            return []

        async def get_session(self, *args: Any, **kwargs: Any) -> SessionInfo | None:
            return None

        async def send_command(self, *args: Any, **kwargs: Any) -> Any:
            return {}

        def subscribe_events(self, *args: Any, **kwargs: Any) -> Any:
            async def _gen() -> Any:
                if False:
                    yield  # type: ignore[unreachable]

            return _gen()

    app = create_app(runtime=_Runtime())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


# ---- 工具函数 --------------------------------------------------------------


def _make_result(
    case_id: str,
    run_id: str = "run-1",
    success: bool = True,
    started_at: str = "2026-01-01T00:00:00",
    finished_at: str = "2026-01-01T00:00:01",
    input_tokens: int = 100,
    output_tokens: int = 50,
    final_answer: str = "ok",
) -> _MockEvalResult:
    """构造 MockEvalResult（agent: package-dashboard-api-v51）。"""
    return _MockEvalResult(
        case_id=case_id,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        success=success,
        final_answer=final_answer,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


# ---- /summary 端点测试 -----------------------------------------------------


# 功能：summary 在无数据时返回全 0 占位
# 设计：fresh store → case_count=0, success_rate=0.0 等占位
def test_summary_empty(client: TestClient) -> None:
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "case_count": 0,
        "success_rate": 0.0,
        "avg_latency_s": 0.0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
    }


# 功能：summary 在有 3 case 时计算 success_rate / avg_latency / tokens / cost
# 设计：3 条 result 写入 store（2 成功 / 1 失败），断言比例与和
def test_summary_with_results(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result("c1", success=True, input_tokens=100, output_tokens=50))
    patch_store.save(_make_result("c2", success=True, input_tokens=200, output_tokens=100))
    patch_store.save(_make_result("c3", success=False, input_tokens=50, output_tokens=25))

    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()

    assert body["case_count"] == 3
    assert body["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
    # 3 case 各自 1 秒延迟，avg = 1.0
    assert body["avg_latency_s"] == pytest.approx(1.0)
    # tokens: (100+50) + (200+100) + (50+25) = 525
    assert body["total_tokens"] == 525
    # cost: (350/1000)*0.003 + (175/1000)*0.015
    expected_cost = round((350 / 1000) * 0.003 + (175 / 1000) * 0.015, 4)
    assert body["total_cost_usd"] == expected_cost


# ---- /runs 端点测试 -------------------------------------------------------


# 功能：runs 端点按 limit/offset 分页返回 run 摘要
# 设计：3 个 run 各 1 case，验证 list_runs 默认按 started_at 倒序
def test_list_runs_default(client: TestClient, patch_store: Any) -> None:
    # run-1: 旧时间
    patch_store.save(_make_result("c1", run_id="run-1", started_at="2026-01-01T00:00:00",
                                   finished_at="2026-01-01T00:00:01"))
    # run-2: 最新
    patch_store.save(_make_result("c2", run_id="run-2", started_at="2026-01-03T00:00:00",
                                   finished_at="2026-01-03T00:00:01"))
    # run-3: 中间
    patch_store.save(_make_result("c3", run_id="run-3", started_at="2026-01-02T00:00:00",
                                   finished_at="2026-01-02T00:00:01"))

    resp = client.get("/api/dashboard/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    # 按 started_at 倒序：run-2 > run-3 > run-1
    run_ids = [r["run_id"] for r in body["runs"]]
    assert run_ids == ["run-2", "run-3", "run-1"]


# ---- /runs/{run_id} 端点测试 ----------------------------------------------


# 功能：runs/{run_id} 不存在时返回 404
# 设计：空 store + 随机 run_id → 404 + detail 含 run_id
def test_get_run_not_found(client: TestClient) -> None:
    resp = client.get("/api/dashboard/runs/missing-run")
    assert resp.status_code == 404
    assert "missing-run" in resp.json()["detail"]


# ---- /metrics/{run_id} 端点测试 -------------------------------------------


# 功能：metrics 端点调用 WT-G2 compute_all_metrics 并返回 7 指标
# 设计：mock compute_all_metrics + EvalCase/EvalDataset 避免依赖未合并模块
def test_get_metrics_7_indicators(client: TestClient, patch_store: Any) -> None:
    # 写入 10 个 case
    for i in range(10):
        patch_store.save(
            _make_result(
                f"c{i}",
                run_id="run-m",
                success=(i % 2 == 0),
                input_tokens=100,
                output_tokens=50,
            )
        )

    # 构造假 Report
    class _FakeReport:
        def to_dict(self) -> dict[str, Any]:
            return {
                "task_success_rate": 0.5,
                "route_accuracy": 0.8,
                "tool_accuracy": 0.7,
                "rag_citation_accuracy": 0.6,
                "avg_latency_s": 1.0,
                "total_tokens": 1500,
                "total_cost_usd": 0.012,
            }

    # 模拟 compute_all_metrics（绕过 WT-G1/G2 依赖）
    fake_report = _FakeReport()
    with (
        patch.dict(
            "sys.modules",
            {
                "kivi_agent.eval.dataset": __import__(
                    "types"
                ).ModuleType("kivi_agent.eval.dataset"),
                "kivi_agent.eval.metrics": __import__(
                    "types"
                ).ModuleType("kivi_agent.eval.metrics"),
                "kivi_agent.eval.metrics.report": __import__(
                    "types"
                ).ModuleType("kivi_agent.eval.metrics.report"),
            },
        ),
    ):
        import sys

        ds_mod = sys.modules["kivi_agent.eval.dataset"]
        rep_mod = sys.modules["kivi_agent.eval.metrics.report"]

        class _FakeCase(BaseModel):
            id: str
            goal: str = ""

        class _FakeDataset(BaseModel):
            name: str
            cases: list[_FakeCase] = []

        ds_mod.EvalCase = _FakeCase  # type: ignore[attr-defined]
        ds_mod.EvalDataset = _FakeDataset  # type: ignore[attr-defined]

        def _fake_compute(_dataset: Any, _results: list[Any]) -> _FakeReport:
            return fake_report

        rep_mod.compute_all_metrics = _fake_compute  # type: ignore[attr-defined]

        resp = client.get("/api/dashboard/metrics/run-m")

    assert resp.status_code == 200
    body = resp.json()
    # 7 个指标都返回
    expected_keys = {
        "task_success_rate",
        "route_accuracy",
        "tool_accuracy",
        "rag_citation_accuracy",
        "avg_latency_s",
        "total_tokens",
        "total_cost_usd",
    }
    assert expected_keys.issubset(body.keys())
    assert body["task_success_rate"] == 0.5


# 功能：metrics 端点在 WT-G1/G2 未合并时返回 501
# 设计：清空 sys.modules 的 dataset/metrics 让 lazy import 失败 → HTTPException 501
def test_get_metrics_501_when_modules_missing(client: TestClient, patch_store: Any) -> None:
    patch_store.save(_make_result("c1", run_id="run-x"))

    with patch.dict(
        "sys.modules",
        {
            "kivi_agent.eval.dataset": None,
            "kivi_agent.eval.metrics": None,
            "kivi_agent.eval.metrics.report": None,
        },
    ):
        resp = client.get("/api/dashboard/metrics/run-x")

    assert resp.status_code == 501
    assert "not available" in resp.json()["detail"]


# ---- /traces/{run_id} 端点测试 --------------------------------------------


# 功能：traces 端点按 case_id 过滤单 case
# 设计：写入 3 case 各自带 events/tool_calls；过滤后只剩 1 case
def test_get_traces_case_filter(client: TestClient, patch_store: Any) -> None:
    r1 = _MockEvalResult(
        case_id="c1",
        run_id="run-t",
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T00:00:01",
        events=[_MockEvent(type="llm.start", ts="t0", data={"x": 1})],
        tool_calls=[_MockToolCall(name="query_database", args={"sql": "SELECT 1"})],
        rag_sources=["doc-1"],
    )
    r2 = _MockEvalResult(
        case_id="c2",
        run_id="run-t",
        started_at="2026-01-01T00:00:02",
        finished_at="2026-01-01T00:00:03",
        events=[],
    )
    r3 = _MockEvalResult(
        case_id="c3",
        run_id="run-t",
        started_at="2026-01-01T00:00:04",
        finished_at="2026-01-01T00:00:05",
    )
    patch_store.save(r1)
    patch_store.save(r2)
    patch_store.save(r3)

    # 不带 case_id：返回 3 case
    resp_all = client.get("/api/dashboard/traces/run-t")
    assert resp_all.status_code == 200
    body_all = resp_all.json()
    assert body_all["trace_count"] == 3
    assert len(body_all["traces"]) == 3

    # 带 case_id=c2：只返回 1 case
    resp = client.get("/api/dashboard/traces/run-t", params={"case_id": "c2"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_count"] == 1
    assert body["traces"][0]["case_id"] == "c2"
    # events / tool_calls / rag_sources 字段都在
    assert "events" in body["traces"][0]
    assert "tool_calls" in body["traces"][0]
    assert "rag_sources" in body["traces"][0]


# ---- 路径遍历保护测试 -----------------------------------------------------


# 功能：run_id 含 `..` 时返回 400（路径遍历保护）
# 设计：覆盖 3 个动态路由；URL 不使用 `%2F`（TestClient 会规范化路径）
def test_path_traversal_run_id(client: TestClient) -> None:
    # runs/{run_id}
    r1 = client.get("/api/dashboard/runs/..bad..")
    assert r1.status_code == 400
    # metrics/{run_id}
    r2 = client.get("/api/dashboard/metrics/..run..")
    assert r2.status_code == 400
    # traces/{run_id}
    r3 = client.get("/api/dashboard/traces/foo..bar..baz")
    assert r3.status_code == 400
    # 错误信息
    assert "invalid run_id" in r1.json()["detail"]


# ---- EvalResultStore 单元测试 ---------------------------------------------


# 功能：EvalResultStore 追加写 + 读取一致
# 设计：存 3 条 → iter_all 返回 3 条 → 字段一致
def test_store_save_and_iter(patch_store: Any) -> None:
    patch_store.save(_make_result("c1", run_id="r1"))
    patch_store.save(_make_result("c2", run_id="r1"))
    patch_store.save(_make_result("c3", run_id="r2"))

    all_results = list(patch_store.iter_all())
    assert len(all_results) == 3
    # 字段保留
    assert all_results[0]["case_id"] == "c1"
    assert all_results[2]["run_id"] == "r2"


# 功能：EvalResultStore.get_run 按 run_id 过滤
# 设计：跨多个 run 写入，get_run 只返回匹配 run_id
def test_store_get_run(patch_store: Any) -> None:
    patch_store.save(_make_result("c1", run_id="r1"))
    patch_store.save(_make_result("c2", run_id="r1"))
    patch_store.save(_make_result("c3", run_id="r2"))

    r1_results = patch_store.get_run("r1")
    assert len(r1_results) == 2
    assert all(r["run_id"] == "r1" for r in r1_results)

    r2_results = patch_store.get_run("r2")
    assert len(r2_results) == 1


# 功能：EvalResultStore 路径遍历保护：拒绝含 `..` 的路径
# 设计：构造恶意 path → 抛 ValueError
def test_store_path_traversal_protection(tmp_path: Path) -> None:
    from kivi_agent.eval.store import EvalResultStore

    bad = tmp_path / ".." / "evil.jsonl"
    with pytest.raises(ValueError, match="invalid store path"):
        EvalResultStore(bad)
