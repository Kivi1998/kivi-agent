"""EvalEmitter — 运行时 → 评估的桥（Wave 1 / E 阶段）。

设计目标（E 报告 T4 + 风险 2 + 风险 7）：
1. **订阅 EventBus**：把"业务 Agent 不知情"的事件流转化为评估记录
2. **多后端**：JSONL 必开（演示版），Redis Streams 可选开关
3. **绝不 hard-fail on import**（E 报告 §700 强制要求）：缺 redis 包时降级
4. **schema_version 守门**：每条事件标 schema_version=v1，下游 consumer 一致

实现策略：
- `EvalEmitter` 本身只做"订阅 + 序列化 + 分发"
- 实际 IO 委托给 `EmitterBackend` 协议（多个实现可插拔）
- JSONL 后端落地到本地文件
- Redis Streams 后端**软依赖**：try/except import；缺包时 `RedisStreamsEmitterBackend is None`

**与 aigroup `EvalEventEmitter` 的差异**（E 报告 §风险 7）：
- aigroup 是**主动 API**（业务代码显式 `record_*`）；kivi 是**被动订阅**（`bus.subscribe`）
- 当前演示版只订阅**已存在的 27 个事件类型**；A 阶段补 `route.decided` /
  `latency.run` 后无需改本类
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel

from kivi_agent.evaluation.contract_version import current_schema_version

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 事件 / 后端协议
# ---------------------------------------------------------------------------

#: 当前 schema 版本（E 阶段 v1）
SCHEMA_VERSION: int = current_schema_version()


@dataclass
class Envelope:
    """评估记录的最小容器。

    所有 backend 共用此格式；序列化时 dump 到 dict。
    """

    schema_version: int = SCHEMA_VERSION
    ts: str = ""
    event_type: str = ""
    run_id: str | None = None
    trace_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    # 序列化为 JSON-safe dict（datetime / BaseModel 都需要兜底）
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ts": self.ts or _now_iso(),
            "event_type": self.event_type,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "payload": _jsonify(self.payload),
        }


class EmitterBackend(Protocol):
    """后端协议：接收一个 Envelope 写入远端。"""

    async def write(self, envelope: Envelope) -> None: ...

    async def flush(self) -> None: ...

    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# JSONL 后端（必开）
# ---------------------------------------------------------------------------

class JsonlEmitterBackend:
    """JSONL 文件后端（演示版默认）。

    每次 `write()` 追加一行；`flush()` 强制刷盘；`close()` 关闭文件。
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()
        self._fp: Any = None  # 延迟到第一次 write 时打开

    # 单条 envelope → 一行 JSON
    async def write(self, envelope: Envelope) -> None:
        async with self._lock:
            if self._fp is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._fp = self._path.open("a", encoding="utf-8", buffering=1)
            line = json.dumps(envelope.to_dict(), ensure_ascii=False)
            self._fp.write(line + "\n")

    # 强刷：跨平台，行缓冲模式下 noop
    async def flush(self) -> None:
        async with self._lock:
            if self._fp is not None:
                self._fp.flush()

    # 关闭文件
    async def close(self) -> None:
        async with self._lock:
            if self._fp is not None:
                self._fp.close()
                self._fp = None


# ---------------------------------------------------------------------------
# Redis Streams 后端（可选）
# ---------------------------------------------------------------------------

#: 软依赖：缺 redis 包时 `RedisStreamsEmitterBackend = None`（绝不能 hard-fail）
#: 提前声明类型：mypy 在 except 分支看不到 `import` 成功的类型，需显式 Any
redis_asyncio: Any
try:
    import redis.asyncio as _redis_asyncio  # type: ignore[import-not-found]

    redis_asyncio = _redis_asyncio
    _REDIS_AVAILABLE: bool = True
except ImportError:  # pragma: no cover
    redis_asyncio = None
    _REDIS_AVAILABLE = False


def redis_available() -> bool:
    """运行时探测 redis 包是否可导入。供配置层决定是否启用。"""
    return _REDIS_AVAILABLE


if _REDIS_AVAILABLE:

    class RedisStreamsEmitterBackend:
        """Redis Streams 后端（XADD 写入 `eval:trace` stream）。

        演示版：单 stream；aigroup 是 3 stream（`eval:trace` / `eval:tool` / `eval:http`），
        后续阶段按需扩展。
        """

        #: 默认 stream 名（与 aigroup 对齐）
        DEFAULT_STREAM: ClassVar[str] = "eval:trace"
        #: XADD 字段名前缀
        _FIELD_PREFIX: ClassVar[str] = "ev_"

        def __init__(
            self,
            url: str = "redis://localhost:6379/0",
            stream: str = DEFAULT_STREAM,
        ) -> None:
            self._url = url
            self._stream = stream
            self._client: Any = None

        # 懒连接（首次 write 时建立）
        async def _ensure_client(self) -> Any:
            if self._client is None:
                self._client = redis_asyncio.from_url(
                    self._url, encoding="utf-8"
                )
            return self._client

        # XADD 写入（field 名扁平化）
        async def write(self, envelope: Envelope) -> None:
            client = await self._ensure_client()
            data = envelope.to_dict()
            # XADD 字段必须是 str/bytes/int/float；嵌套 dict 需 JSON 序列化
            fields: dict[str, str] = {}
            for k, v in data.items():
                if isinstance(v, str):
                    fields[self._FIELD_PREFIX + k] = v
                elif isinstance(v, bool):
                    # bool 优先于 int，单独处理
                    fields[self._FIELD_PREFIX + k] = "true" if v else "false"
                elif isinstance(v, (int, float)):
                    fields[self._FIELD_PREFIX + k] = str(v)
                else:
                    fields[self._FIELD_PREFIX + k] = json.dumps(
                        v, ensure_ascii=False
                    )
            await client.xadd(self._stream, fields)

        async def flush(self) -> None:
            # Redis client 自身是 async 写，flush 语义不适用
            return

        async def close(self) -> None:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

else:  # pragma: no cover

    class RedisStreamsEmitterBackend:  # type: ignore[no-redef]
        """占位实现：redis 包不可用时实例化会立即报错（fail-loud 但不 fail-on-import）。

        注：本类仅在 `redis_available() is False` 时被引用；导入 evaluation 包不会触发。
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "RedisStreamsEmitterBackend 不可用：'redis' 包未安装。"
                "安装 `redis>=5.0` 后再启用 Redis 后端；"
                "或保持 JSONL 后端（演示版默认）。"
            )


# ---------------------------------------------------------------------------
# EvalEmitter 主体
# ---------------------------------------------------------------------------

#: 事件类型提取函数（pydantic 模型都有 .type 字段；回退到类名）
def _event_type_of(event: BaseModel) -> str:
    return getattr(event, "type", event.__class__.__name__)


#: 通用事件 → envelope payload 的转换
def _event_to_payload(event: BaseModel) -> dict[str, Any]:
    if isinstance(event, BaseModel):
        return event.model_dump(mode="json")
    # 兜底：纯对象 → __dict__
    return {k: v for k, v in event.__dict__.items() if not k.startswith("_")}


@dataclass
class EvalEmitterConfig:
    """EvalEmitter 配置。

    关键开关：
    - `backend`: "jsonl" | "redis"（默认 jsonl）
    - `jsonl_path`: JSONL 后端输出路径
    - `redis_url` / `redis_stream`: Redis 后端参数（仅在 backend="redis" 时生效）
    """

    backend: str = "jsonl"
    jsonl_path: Path = field(default_factory=lambda: Path("./eval-events.jsonl"))
    redis_url: str = "redis://localhost:6379/0"
    redis_stream: str = RedisStreamsEmitterBackend.DEFAULT_STREAM \
        if _REDIS_AVAILABLE else "eval:trace"
    # 事件采样率（0.0-1.0），演示版默认全量
    sample_rate: float = 1.0
    # 是否在 publish 时立即 flush
    flush_on_write: bool = False


class EvalEmitter:
    """EvalEmitter — 订阅 EventBus，把事件序列化到后端。

    典型用法：
        bus = EventBus()
        emitter = EvalEmitter(bus=bus, config=EvalEmitterConfig())
        await emitter.start()
        # ... 业务代码 publish 事件 ...
        await emitter.stop()

    行为保证：
    - `start()` 注册订阅者；handler 异步执行，不阻塞 publisher
    - `stop()` 取消订阅并 flush 后端
    - handler 异常**仅记日志**，不传播到 publisher
    - 后端异常（如磁盘满）也仅记日志，下一条事件继续尝试
    """

    def __init__(
        self,
        *,
        bus: Any,  # EventBus-like（有 .subscribe）
        config: EvalEmitterConfig | None = None,
        backend: EmitterBackend | None = None,
    ) -> None:
        self._bus = bus
        self._config = config or EvalEmitterConfig()
        self._backend: EmitterBackend = backend or self._build_default_backend()
        self._running = False

    # 默认后端工厂
    def _build_default_backend(self) -> EmitterBackend:
        if self._config.backend == "redis":
            if not _REDIS_AVAILABLE:
                log.warning(
                    "配置指定 Redis 后端但 'redis' 包未安装；"
                    "降级到 JSONL 后端（演示版路径）"
                )
                return JsonlEmitterBackend(self._config.jsonl_path)
            return RedisStreamsEmitterBackend(
                url=self._config.redis_url,
                stream=self._config.redis_stream,
            )
        return JsonlEmitterBackend(self._config.jsonl_path)

    # 启动：注册订阅
    async def start(self) -> None:
        if self._running:
            return
        self._bus.subscribe(self._on_event)
        self._running = True

    # 停止：取消订阅 + flush + close
    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        await self._backend.flush()
        await self._backend.close()

    # 同步停止（context manager 友好）
    def stop_sync(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.stop())
        except RuntimeError:
            # 无 event loop（极少数情况）：直接关文件
            asyncio.run(self.stop())

    # EventBus 订阅 handler
    async def _on_event(self, event: BaseModel) -> None:
        envelope = Envelope(
            event_type=_event_type_of(event),
            run_id=getattr(event, "run_id", None),
            trace_id=getattr(event, "trace_id", None),
            payload=_event_to_payload(event),
        )
        try:
            await self._backend.write(envelope)
            if self._config.flush_on_write:
                await self._backend.flush()
        except Exception as exc:  # noqa: BLE001
            # 兜底：单条事件失败不污染整个 publisher
            log.warning("EvalEmitter 后端写入失败: %s", exc)

    # 暴露后端，便于测试断言
    @property
    def backend(self) -> EmitterBackend:
        return self._backend


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


#: 把对象转 JSON-safe（pydantic / datetime / 自定义类）
def _jsonify(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # 兜底：str(obj)
    return str(obj)
