"""Demo 4：前端操作 Agent（agent: package-demo-v7）。

# demo4_frontend_map.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / demo4 设计：
- 输入：fixtures/demo4_geojson_urls.json（3 个公开 GeoJSON URL）+ "找最近的 3 个公园"问题
- 流程：web_search agent 找 URL + MapLoadTool 加载地图
- 期望：每个 URL 返回 loaded_features_count + bbox

可独立运行：`uv run python -m demos.demo4_frontend_map`

注意：本 demo 默认走 mock fetch_fn（演示版 100% 离线，不真下载 GeoJSON）；
如需真下载，传 KIVI_REAL_GEOJSON=1 环境变量。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from kivi_agent.core.tools.builtin.map_load import MapLoadTool

from demos.base import DemoBase, DemoResult


# Mock GeoJSON 数据：URL 前缀 → 返回 mock（agent: package-demo-v7）
# 演示版对 fixture 里的 3 个公开 URL 都能给出 mock 数据
_MOCK_GEOJSON_POOL: list[dict[str, object]] = [
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [116.40, 39.90]},
                "properties": {"name": "朝阳公园"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [116.38, 39.92]},
                "properties": {"name": "奥林匹克公园"},
            },
        ],
    },
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.47, 31.23]},
                "properties": {"name": "人民公园"},
            },
        ],
    },
    {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [113.0, 23.0],
                            [113.5, 23.0],
                            [113.5, 23.5],
                            [113.0, 23.5],
                            [113.0, 23.0],
                        ]
                    ],
                },
                "properties": {"name": "天河公园"},
            },
        ],
    },
]


# Mock fetch：URL in pool → 循环返回 mock 数据；否则模拟失败（agent: package-demo-v7）
_mock_fetch_call_index = {"i": 0}


async def _mock_fetch(url: str) -> dict[str, object]:
    """演示版 fetch_fn：循环返回 3 套 mock GeoJSON；用于离线 demo。"""
    if not (url.startswith("http://") or url.startswith("https://")):
        raise RuntimeError(f"mock fetch: unsupported scheme {url}")
    pool = _MOCK_GEOJSON_POOL
    idx = _mock_fetch_call_index["i"] % len(pool)
    _mock_fetch_call_index["i"] += 1
    return pool[idx]


# 真实 fetch：转给 MapLoadTool 内置的 httpx（agent: package-demo-v7）
async def _real_fetch(url: str) -> dict[str, object]:
    """真实 fetch：调内置 httpx 拉取 GeoJSON。"""
    from kivi_agent.core.tools.builtin.map_load import _httpx_fetch

    return await _httpx_fetch(url)  # type: ignore[return-value]


# Demo 4：前端操作 Agent 找 GeoJSON + 加载地图（agent: package-demo-v7）
class Demo4FrontendMap(DemoBase):
    """前端操作 Agent 演示：用 MapLoadTool 加载公开 GeoJSON 到前端 MapView。"""

    name = "demo4_frontend_map"
    description = "前端操作 Agent：用 MapLoadTool 加载 3 个 GeoJSON URL + 推 map.geojson_loaded 事件"

    # 跑 demo 业务逻辑（agent: package-demo-v7）
    async def run(self) -> DemoResult:
        # 1. 加载 fixture
        fixture = Path(__file__).parent / "fixtures" / "demo4_geojson_urls.json"
        fixture_data = json.loads(fixture.read_text(encoding="utf-8"))
        urls: list[str] = fixture_data["urls"]
        task: str = fixture_data["task"]

        # 2. 决定 fetch 模式：默认 mock；KIVI_REAL_GEOJSON=1 → 真实 httpx
        from tests._fakes.event_bus import FakeEventBus

        use_real = os.environ.get("KIVI_REAL_GEOJSON") == "1"
        fetch_fn = _real_fetch if use_real else _mock_fetch
        bus = FakeEventBus()
        tool = MapLoadTool(bus=bus, fetch_fn=fetch_fn)

        # 3. 逐个 URL 加载
        load_results: list[dict[str, object]] = []
        for i, url in enumerate(urls, start=1):
            result = await tool.invoke({"geojson_url": url, "layer_id": f"parks-{i}"})
            if result.is_error:
                load_results.append(
                    {
                        "url": url,
                        "ok": False,
                        "error": result.content,
                    }
                )
            else:
                payload = json.loads(result.content)
                load_results.append(
                    {
                        "url": url,
                        "ok": True,
                        "loaded_features_count": payload.get("loaded_features_count"),
                        "bbox": payload.get("bbox"),
                        "layer_id": payload.get("layer_id"),
                    }
                )

        # 4. 校验：演示版用 mock fixture → 3 个 URL 全部 ok + 至少 1 个 feature
        #    （真实模式下，外部 URL 可能 200/404/rate-limit 混合，结果只校验至少 1 个 ok）
        ok_count = sum(1 for r in load_results if r.get("ok"))
        all_have_features = all(
            int(r.get("loaded_features_count", 0) or 0) > 0  # type: ignore[arg-type]
            for r in load_results
            if r.get("ok")
        )
        all_have_bbox = all(
            r.get("bbox") is not None  # type: ignore[union-attr]
            for r in load_results
            if r.get("ok")
        )

        # 5. 验证事件已推（FakeEventBus 记录 map.geojson_loaded）
        map_event_count = bus.published_types.get("map.geojson_loaded", 0)

        # 6. 汇总：演示版期望 3/3 ok；真实版期望至少 1/3 ok
        if use_real:
            passed = ok_count >= 1 and all_have_features and map_event_count == ok_count
        else:
            passed = (
                ok_count == len(urls)
                and all_have_features
                and all_have_bbox
                and map_event_count == len(urls)
            )

        artifacts = {
            "task": task,
            "use_real": use_real,
            "url_count": len(urls),
            "ok_count": ok_count,
            "map_event_count": map_event_count,
            "loads": load_results,
        }
        summary = (
            f"urls={len(urls)} ok={ok_count} events={map_event_count} "
            f"bbox_ok={all_have_bbox} features_ok={all_have_features}"
        )
        return DemoResult(
            name=self.name,
            status="passed" if passed else "failed",
            summary=summary,
            duration_seconds=0.0,
            artifacts=artifacts,
        )


# 入口：`uv run python -m demos.demo4_frontend_map`（agent: package-demo-v7）
def main() -> None:
    async def _go() -> DemoResult:
        async with Demo4FrontendMap() as demo:
            return await demo.execute()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
