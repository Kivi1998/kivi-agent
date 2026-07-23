"""MapLoadTool：前端地图加载工具（agent: package-demo-v7）。

# map_load.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / 新做 frontend_map Tool 设计：
- 输入：geojson_url（公开 URL）
- 输出：loaded_features_count / bbox / 推 `map.geojson_loaded` 事件
- category = "read"（只读：拉取 + 解析 + 推送，不修改任何状态）

设计要点：
- HTTP 拉取走 `httpx.AsyncClient`（已在 dev deps），不在 sandbox 限制范围内
  （因为是公开 URL + 演示版只读 GET；真实版应配 AllowList）
- 解析 GeoJSON：找 features 数组；缺则视为空集合
- bbox 计算：扫 coordinates 算 min/max（仅支持 Point / Polygon / MultiPolygon 顶层）
- 事件推送：构造时注入 EventBus；bus=None → 哑模式（不推）
- 路径保护：拒绝 file:// / 私有网段 / localhost URL（防止 SSRF）

未来切真前端：
- 替换 _fetch_geojson 走真实 fetch
- 加 layer_id / projection 等参数
"""
from __future__ import annotations

import json
import logging
import math
from ipaddress import ip_address
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult

log = logging.getLogger(__name__)


# 任何有 publish() 方法的对象（兼容生产 EventBus 与 FakeEventBus）
class _BusLike(Protocol):
    """EventBus 协议（duck-typed on `publish`）。"""

    async def publish(self, event: Any) -> None: ...


# 阻止解析私有 / 回环网段 URL（防止 SSRF；演示版也保留这道安全网）
_DISALLOWED_HOSTNAMES: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}
)
_DISALLOWED_SCHEMES: frozenset[str] = frozenset({"file", "ftp", "data"})


# 校验 URL 是否为可访问的公开 http(s) URL
def _validate_geojson_url(url: str) -> str | None:
    """返回错误消息或 None（None = 通过）。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return f"invalid URL: {url}"
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme: {parsed.scheme!r} (only http/https)"
    if parsed.scheme in _DISALLOWED_SCHEMES:
        return f"disallowed scheme: {parsed.scheme!r}"
    if not parsed.netloc:
        return f"missing host: {url}"
    host = (parsed.hostname or "").lower()
    if host in _DISALLOWED_HOSTNAMES:
        return f"blocked host (private/loopback): {host}"
    # IP 字面量：阻止私有 / 回环 / link-local
    try:
        ip = ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return f"blocked IP (private/reserved): {host}"
    except ValueError:
        pass  # 不是字面量 IP，跳过
    return None


# 解析 GeoJSON features + bbox
def _parse_features(geojson: dict[str, Any]) -> tuple[int, list[float] | None]:
    """返回 (features_count, bbox) —— bbox 形如 [min_lon, min_lat, max_lon, max_lat]。

    bbox 算法：扫所有 features，递归找所有数字对（lon, lat）；不支持三维坐标。
    """
    features = geojson.get("features", [])
    if not isinstance(features, list):
        return 0, None

    min_lon = math.inf
    min_lat = math.inf
    max_lon = -math.inf
    max_lat = -math.inf
    found_any = False

    def _scan_coords(coords: Any) -> None:
        nonlocal min_lon, min_lat, max_lon, max_lat, found_any
        if isinstance(coords, (int, float)):
            # 标量：单点（不常见，跳过）
            return
        if not isinstance(coords, (list, tuple)):
            return
        # 嵌套：递归
        if len(coords) >= 2 and all(isinstance(x, (int, float)) for x in coords[:2]):
            lon, lat = float(coords[0]), float(coords[1])
            min_lon = min(min_lon, lon)
            min_lat = min(min_lat, lat)
            max_lon = max(max_lon, lon)
            max_lat = max(max_lat, lat)
            found_any = True
            return
        for c in coords:
            _scan_coords(c)

    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        if not isinstance(geom, dict):
            continue
        _scan_coords(geom.get("coordinates"))

    bbox: list[float] | None = None
    if found_any and min_lon != math.inf:
        bbox = [min_lon, min_lat, max_lon, max_lat]
    return len(features), bbox


# map_load 输入参数（agent: package-demo-v7）
class MapLoadParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    geojson_url: str
    layer_id: str = "default"


# 演示版 frontend_map Tool：拉公开 GeoJSON + 算 bbox + 推 `map.geojson_loaded` 事件（agent: package-demo-v7）
class MapLoadTool(BaseTool):
    """map_load Tool：拉取公开 GeoJSON，解析 features + bbox，推 map.geojson_loaded 事件。

    副作用：构造时注入 EventBus；bus=None 时不推事件（哑模式）。
    真实模式：调 `httpx.AsyncClient.get(geojson_url, timeout=10, follow_redirects=True)`。
    Mock 模式：构造时传 `fetch_fn`，不调外部网络（测试用）。
    """

    params_model = MapLoadParams
    name = "map_load"
    category = "read"  # 只读 GET，无写
    description = (
        "Load a public GeoJSON URL into the frontend map. "
        "Returns the number of features loaded and the bounding box [min_lon, min_lat, max_lon, max_lat]. "
        "Emits a 'map.geojson_loaded' event so the MapView component can render the layer. "
        "Only http(s) public URLs are allowed; private/loopback hosts are blocked."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "geojson_url": {
                "type": "string",
                "description": "A public http(s) URL pointing to a GeoJSON document.",
            },
            "layer_id": {
                "type": "string",
                "description": "Optional layer identifier (default 'default').",
            },
        },
        "required": ["geojson_url"],
    }

    # 初始化：注入 EventBus + 可选 fetch 覆盖（Mock 用）
    def __init__(
        self,
        bus: _BusLike | None = None,
        fetch_fn: Any = None,  # async (url) -> dict (mock 模式注入)
    ) -> None:
        self._bus = bus
        # fetch_fn 不传 → 默认用 httpx 真实拉取；mock 模式传 lambda
        self._fetch_fn = fetch_fn

    # 入口：参数校验 → 拉取 → 解析 → 推事件 → 返回 JSON
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = MapLoadParams.model_validate(params)
        except Exception as e:  # noqa: BLE001
            return ToolResult(
                content=json.dumps(
                    {"error": "invalid_params", "detail": str(e)}, ensure_ascii=False
                ),
                is_error=True,
                error_type="schema_error",
            )

        # 1. URL 安全校验
        url_err = _validate_geojson_url(p.geojson_url)
        if url_err is not None:
            return ToolResult(
                content=json.dumps({"error": "blocked_url", "detail": url_err}, ensure_ascii=False),
                is_error=True,
                error_type="permission_denied",
            )

        # 2. 拉 GeoJSON
        try:
            if self._fetch_fn is not None:
                geojson = await self._fetch_fn(p.geojson_url)
            else:
                geojson = await _httpx_fetch(p.geojson_url)
        except Exception as e:  # noqa: BLE001
            log.warning("map_load fetch failed url=%s err=%s", p.geojson_url, e)
            return ToolResult(
                content=json.dumps(
                    {"error": "fetch_failed", "url": p.geojson_url, "detail": str(e)},
                    ensure_ascii=False,
                ),
                is_error=True,
                error_type="runtime_error",
            )

        if not isinstance(geojson, dict):
            return ToolResult(
                content=json.dumps(
                    {"error": "invalid_geojson", "detail": "not a JSON object"}, ensure_ascii=False
                ),
                is_error=True,
                error_type="schema_error",
            )

        # 3. 解析 features + bbox
        feat_count, bbox = _parse_features(geojson)

        # 4. 推 `map.geojson_loaded` 事件
        if self._bus is not None:
            try:
                await self._bus.publish(
                    _make_geojson_loaded_event(
                        url=p.geojson_url,
                        layer_id=p.layer_id,
                        features_count=feat_count,
                        bbox=bbox,
                    )
                )
            except Exception as e:  # noqa: BLE001 — 推事件失败不影响主返回
                log.warning("map_load event publish failed: %s", e)

        # 5. 返回结构化结果
        return ToolResult(
            content=json.dumps(
                {
                    "url": p.geojson_url,
                    "layer_id": p.layer_id,
                    "loaded_features_count": feat_count,
                    "bbox": bbox,
                },
                ensure_ascii=False,
            )
        )


# 真实拉取：httpx async GET（agent: package-demo-v7）
async def _httpx_fetch(url: str) -> dict[str, Any]:
    """用 httpx 拉取 GeoJSON；返回 dict（调用方需判断有效性）。"""
    import httpx

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


# 构造 `map.geojson_loaded` 事件（agent: package-demo-v7）
def _make_geojson_loaded_event(
    url: str, layer_id: str, features_count: int, bbox: list[float] | None
) -> Any:
    """构造一个最小事件（pydantic BaseModel，便于 EventBus 透传；非 pydantic 也降级为 dict）。"""
    try:
        from pydantic import BaseModel as _BM

        class _GeojsonLoadedEvent(_BM):
            type: str = "map.geojson_loaded"
            url: str
            layer_id: str
            features_count: int
            bbox: list[float] | None
            ts: str

        return _GeojsonLoadedEvent(
            url=url,
            layer_id=layer_id,
            features_count=features_count,
            bbox=bbox,
            ts=_now_iso(),
        )
    except Exception:  # noqa: BLE001
        # 兜底：返回 dict（不推荐但兼容）
        return {
            "type": "map.geojson_loaded",
            "url": url,
            "layer_id": layer_id,
            "features_count": features_count,
            "bbox": bbox,
            "ts": _now_iso(),
        }


# 当前 UTC 时间的 ISO 8601 字符串（agent: package-demo-v7）
def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
