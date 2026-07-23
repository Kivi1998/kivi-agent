"""RouteDecision 展示面板（agent: package-tui-route-v2）。

业务 Router 把 query 路由到哪些 Profile：单/多意图标识 + 置信度 + 匹配关键词。
供 TUI 主循环在用户提交 query 后挂载，实时显示路由决策。
集成位置：主 agent 在 KamaTuiApp._handle_event_inner 中按 run.started 事件挂载。
"""
from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from kivi_agent.core.agents.business_router import RouteDecision

# 仅保留安全字符作为 widget DOM id；避免 query 中出现 `/` `\\` `..` 等导致 id/CSS 解析异常
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")


# 用 query 前缀生成一个安全且可读性尚可的 widget id；防御特殊字符 + 限制长度
def _safe_widget_id(query: str) -> str:
    cleaned = _SAFE_ID_RE.sub("_", query.strip())[:24].strip("_")
    return f"route-panel-{cleaned or 'unknown'}"


class RoutePanel(Container):
    """路由决策面板：展示 query → target_profiles 的完整决策。"""

    DEFAULT_CSS = """
    RoutePanel {
        height: auto;
        border: round cyan;
        padding: 0 1;
    }
    RoutePanel .route-header {
        color: cyan;
        text-style: bold;
    }
    RoutePanel .route-profiles {
        color: white;
    }
    RoutePanel .multi-intent {
        color: yellow;
    }
    RoutePanel .route-meta {
        color: $text-muted;
    }
    """

    # 用路由决策初始化面板；widget id 由 query 派生，便于按 run 在 TUI 树中定位
    def __init__(self, decision: RouteDecision) -> None:
        super().__init__(id=_safe_widget_id(decision.query))
        self._decision = decision

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), classes="route-header")
        yield Static(self._profiles_text(), classes="route-profiles")
        if self._decision.is_multi_intent:
            yield Static(
                "⚠ 多意图（按优先级排序，synthesizer 兜底汇总）",
                classes="multi-intent",
            )
        yield Static(self._meta_text(), classes="route-meta")

    # 渲染头部行：intent 名称 + 置信度（保留两位小数便于快速肉眼对比）
    def _header_text(self) -> str:
        return (
            f"🧭 路由决策  intent={self._decision.intent}  "
            f"confidence={self._decision.confidence:.2f}"
        )

    # 渲染 profile 链路：用 → 连接 chip 风格标记，保留 Router 给出的优先级顺序
    def _profiles_text(self) -> str:
        chips = " → ".join(
            f"[reverse bold]{p}[/reverse bold]" for p in self._decision.target_profiles
        )
        return f"profiles: {chips}"

    # 渲染底部元信息：列出命中关键词；空集时给出显式占位文本，避免 UI 出现空段
    def _meta_text(self) -> str:
        kw = ", ".join(self._decision.matched_keywords) or "(无关键词匹配)"
        return f"matched: {kw}"


__all__ = ["RoutePanel"]
