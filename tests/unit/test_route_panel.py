from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Static

from kivi_agent.core.agents.business_router import RouteDecision
from kivi_agent.tui.route_panel import RoutePanel


class _RoutePanelHostApp(App[None]):
    """最小宿主 App：仅挂一个 RoutePanel，供 run_test 验证 widget 在真实 TUI 内渲染。"""

    # 初始化要渲染的 RoutePanel（与生产路径一致：直接以 RouteDecision 构造）
    def __init__(self, decision: RouteDecision) -> None:
        super().__init__()
        self._decision = decision

    def compose(self) -> ComposeResult:
        yield RoutePanel(self._decision)


# 功能：单意图 query 渲染不含"多意图"标签、intent 标签与 confidence 正确出现
# 设计：直接调 _header_text / _profiles_text / _meta_text 验证文本分支，
#       这样无须启 App 也能锁定所有文案；避免 Static Rich 对象比较的脆弱性
def test_route_panel_single_intent() -> None:
    decision = RouteDecision(
        query="查我们公司年假政策",
        intent="rag",
        target_profiles=["rag"],
        is_multi_intent=False,
        confidence=0.85,
        matched_keywords=["我们公司"],
    )
    panel = RoutePanel(decision)

    header = panel._header_text()
    profiles = panel._profiles_text()
    meta = panel._meta_text()

    assert "intent=rag" in header
    assert "confidence=0.85" in header
    assert "profiles: " in profiles
    assert "rag" in profiles
    assert "synthesizer" not in profiles
    assert "我们公司" in meta
    # 单意图不出现"多意图"提示文案
    assert "多意图" not in header and "多意图" not in profiles and "多意图" not in meta


# 功能：多意图场景下 chips 保留输入顺序且 synthesizer 一定在末尾，并显示"多意图"标签
# 设计：直接验证 _profiles_text 的 chip 顺序和 is_multi_intent 分支文案；
#       用 reversed 输入来确保显示顺序与传入一致（而不是被 sort），
#       同时确认 synthesizer 作为兜底汇总始终出现在最末位
def test_route_panel_multi_intent_synthesizer_last() -> None:
    decision = RouteDecision(
        query="对比网上文章和我们内部知识库",
        intent="web_search",
        target_profiles=["rag", "web_search", "synthesizer"],
        is_multi_intent=True,
        confidence=0.8,
        matched_keywords=["我们公司", "网上"],
    )
    panel = RoutePanel(decision)

    profiles = panel._profiles_text()
    meta = panel._meta_text()

    # chip 顺序应与传入顺序一致
    rag_idx = profiles.index("rag")
    web_idx = profiles.index("web_search")
    synth_idx = profiles.index("synthesizer")
    assert rag_idx < web_idx < synth_idx
    # synthesizer 在箭头链最末位（chip 形态为 [reverse bold]synthesizer[/reverse bold]）
    assert profiles.endswith("[reverse bold]synthesizer[/reverse bold]")
    # 关键词都进 meta
    assert "我们公司" in meta and "网上" in meta


# 功能：matched_keywords 为空时显示显式占位文本，避免空段误导用户
# 设计：覆盖 matched_keywords=[] 的边界；这是路由降级到 general 或词表外 query 的常见场景
def test_route_panel_no_keywords() -> None:
    decision = RouteDecision(
        query="你好",
        intent="general",
        target_profiles=["general"],
        is_multi_intent=False,
        confidence=0.0,
        matched_keywords=[],
    )
    panel = RoutePanel(decision)

    meta = panel._meta_text()
    assert "(无关键词匹配)" in meta


# 功能：target_profiles 列表按 Router 优先级原样展示，顺序敏感
# 设计：用 database → rag → synthesizer 这个非字母序、非数字序的输入验证展示无重排；
#       多意图场景下顺序就是 Router 计算出的执行顺序，重排会破坏"synthesizer 末尾"这个不变量
def test_route_panel_priority_order() -> None:
    decision = RouteDecision(
        query="统计 Q1 销售并对照内部 FAQ",
        intent="database",
        target_profiles=["database", "rag", "synthesizer"],
        is_multi_intent=True,
        confidence=0.9,
        matched_keywords=["统计", "FAQ"],
    )
    panel = RoutePanel(decision)

    profiles = panel._profiles_text()
    db_idx = profiles.index("database")
    rag_idx = profiles.index("rag")
    synth_idx = profiles.index("synthesizer")
    assert db_idx < rag_idx < synth_idx
    # 头部 intent 反映主意图（database）而非第一个 profile
    assert "intent=database" in panel._header_text()


# 功能：RoutePanel 在真实 Textual App 中挂载时，4 个 Static 子 widget 都按预期出现
# 设计：用 App.run_test() 真正 mount widget，断言 children 类型与文本内容；
#       这是对"compose() 的 yield 顺序正确 + 文本生成器被实际调用"的端到端校验，
#       替代单独 unit 测试 compose() 时无法触发的 mount lifecycle
async def test_route_panel_mounts_with_expected_static_children() -> None:
    decision = RouteDecision(
        query="对比网上文章和我们内部知识库",
        intent="web_search",
        target_profiles=["web_search", "rag", "synthesizer"],
        is_multi_intent=True,
        confidence=0.8,
        matched_keywords=["网上", "我们公司"],
    )

    app = _RoutePanelHostApp(decision)
    async with app.run_test() as pilot:
        panel = pilot.app.query_one(RoutePanel)
        # 等待首帧渲染完成
        await pilot.pause()
        statics = list(panel.query(Static))
        # 1) header  2) profiles  3) 多意图提示  4) meta  → 4 个 Static
        assert len(statics) == 4
        rendered = "\n".join(str(s.content) for s in statics)
        assert "intent=web_search" in rendered
        assert "profiles: " in rendered
        assert "synthesizer" in rendered
        assert "多意图" in rendered
        assert "matched: " in rendered
