"""5 个业务 Profile（general / rag / web_search / database / synthesizer）加载 + 字段契约硬断言。

- 覆盖 v1 §3 AgentProfile 10 字段（含 5 个扩展字段）
- 覆盖 Wave 2 plan §3 冻结的 system_prompt 主题
- 5 个 Profile 路径位于 src/kivi_agent/core/agents/builtin/business/
"""
from __future__ import annotations

import pytest

from kivi_agent.core.agents.loader import AgentProfile, AgentProfileLoader

# v1 §1 冻结的 6 个业务 Tool 名（所有业务 Tool 绑定测试都用此常量）
BUSINESS_TOOLS: frozenset[str] = frozenset(
    {"web_search", "rag_query", "query_database", "echarts_render", "memory_save", "memory_recall"}
)

# Wave 2 plan §3 冻结的 5 个业务 Profile 名
BUSINESS_PROFILE_NAMES: list[str] = ["general", "rag", "web_search", "database", "synthesizer"]


# ─────────────────────────── 5 个 TOML 文件存在 + 加载 ───────────────────────────


# 功能：5 个业务 Profile TOML 文件应全部存在于 builtin/business/ 目录
# 设计：直接读 _BUILTIN_DIR 子目录文件名，避免依赖 loader 的子目录扫描逻辑（防回归）
def test_business_toml_files_exist() -> None:
    loader = AgentProfileLoader()
    business_dir = loader._BUILTIN_DIR / "business"
    assert business_dir.is_dir(), f"business subdir missing: {business_dir}"
    found = {p.stem for p in business_dir.glob("*.toml")}
    expected = set(BUSINESS_PROFILE_NAMES)
    assert expected <= found, f"missing TOML: {expected - found}"


# 功能：5 个业务 Profile 都能被 AgentProfileLoader.load(name) 加载
# 设计：参数化覆盖每个 name；直接断言 profile is not None，不重复断言字段（字段在下面专门测）
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_loadable(name: str) -> None:
    loader = AgentProfileLoader()
    profile = loader.load(name)
    assert profile is not None, f"business profile '{name}' not loadable"


# ─────────────────────────── 5 Profile 基础字段契约 ───────────────────────────


# 功能：5 个业务 Profile 的 name 字段等于文件名（去掉 .toml）
# 设计：parametrize 覆盖；防回归——loader 的 name 参数必须传到 AgentProfile.name
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_name_matches(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert profile.name == name


# 功能：5 个业务 Profile 的 description 非空且为中文
# 设计：description 是 router 路由决策可见的元信息；空 description 会让上层分类器无法识别；
#      简易启发式：含至少一个中文字符（0x4E00-0x9FFF）即视为中文
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_description_nonempty_chinese(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert profile.description != "", f"{name} description empty"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in profile.description), (
        f"{name} description not Chinese: {profile.description!r}"
    )


# 功能：5 个业务 Profile 的 system_prompt 非空
# 设计：system_prompt 是 LLM 行为的唯一指令源；空 prompt 等于让模型裸跑
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_system_prompt_nonempty(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert profile.system_prompt.strip() != "", f"{name} system_prompt empty"


# 功能：5 个业务 Profile 的 allowed_tools 至少包含 read_file（最低只读基线）
# 设计：所有业务 Profile 都应能读本地文件；缺失意味着拿不到上下文
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_has_read_file(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert "read_file" in profile.allowed_tools, (
        f"{name} missing read_file in allowed_tools: {profile.allowed_tools}"
    )


# 功能：5 个业务 Profile 的 allowed_tools 至少有一个元素
# 设计：len(allowed_tools)==0 是合法 dataclass 默认值，但业务 Profile 必须能用至少一个工具
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_allowed_tools_nonempty(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert len(profile.allowed_tools) > 0, f"{name} allowed_tools empty"


# 功能：5 个业务 Profile 沿用 coordinator 范式的 model 字段
# 设计：model="" 是 dataclass 默认值，但业务 Profile 必须显式指定模型；
#      硬编码 "claude-sonnet-4-6" 防止有人改 model 字段而不更新测试
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_model_field(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert profile.model == "claude-sonnet-4-6", (
        f"{name} model drift: {profile.model!r}"
    )


# ─────────────────────────── v1 §3 5 扩展字段契约 ───────────────────────────


# 功能：5 个业务 Profile 的 v1 §3 5 扩展字段都被正确解析（非默认）
# 设计：每个业务 Profile 必须显式设 max_steps + category；permission_mode 显式设为 "default"；
#      result_schema 留 None；concurrency_group 用 "business_xxx" 命名；
#      抓"未来有人在 TOML 漏写这些字段"的回归
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_v1_extension_fields_parsed(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    # max_steps 必须在 1~100 区间（防止有人写 0 或 10000）
    assert 1 <= profile.max_steps <= 100, (
        f"{name} max_steps out of range: {profile.max_steps}"
    )
    # permission_mode 必须可解析（dataclass 已验证）
    assert profile.permission_mode is not None
    # result_schema 留 None（业务 Profile 不需要 LLM 结构化输出 schema）
    assert profile.result_schema is None, (
        f"{name} unexpectedly has result_schema: {profile.result_schema}"
    )
    # concurrency_group 必须以 business_ 前缀（业务 Profile 命名空间）
    assert profile.concurrency_group.startswith("business_"), (
        f"{name} concurrency_group should start with 'business_': {profile.concurrency_group}"
    )
    # category 必须是 v1 §3 4 个合法字面量
    assert profile.category in {"read", "write", "command", "other"}, (
        f"{name} category invalid: {profile.category}"
    )


# 功能：5 个业务 Profile 的 max_steps 都小于等于 25（业务调用通常 1-2 跳完成）
# 设计：max_steps 越大单次 run 越重；业务 Profile 默认走 router 链路，单 agent 不应跑太多步
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_max_steps_reasonable(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert profile is not None
    assert profile.max_steps <= 25, f"{name} max_steps too high: {profile.max_steps}"


# 功能：5 个业务 Profile 的 category 字段是合法 v1 字面量（强类型层）
# 设计：用 dataclass 构造期验证防回归；category 字段本身在 loader._parse 走 dict.get
#      默认 "other"，如果业务 TOML 误写 "Read"（大小写错）会被 dataclass 类型拒绝
def test_business_profile_categories_typed() -> None:
    expected_categories = {
        "general": "other",  # 通用助手可读可写可命令，混合型
        "rag": "read",       # 知识库检索只读
        "web_search": "read",  # 联网搜索只读
        "database": "read",    # 问数只读（含 echarts_render 是元数据生成，不算写副作用）
        "synthesizer": "read",  # 合成助手只读
    }
    for name, expected in expected_categories.items():
        profile = AgentProfileLoader().load(name)
        assert profile is not None
        assert profile.category == expected, (
            f"{name} category={profile.category!r}, expected {expected!r}"
        )


# ─────────────────────────── 5 Profile 的 system_prompt 主题契约 ───────────────────────────


# 功能：synthesizer 的 system_prompt 必须明确声明不调任何业务 Tool
# 设计：抓"synthesizer 误绑业务 Tool"或"system_prompt 漏写边界"的回归；
#      关键词匹配是简单稳定的方式，比 LLM 评估更可测
def test_synthesizer_prompt_states_no_business_tool() -> None:
    profile = AgentProfileLoader().load("synthesizer")
    assert profile is not None
    # 必须出现"不调" + "业务 Tool" 或类似字样
    prompt = profile.system_prompt
    assert "不调" in prompt or "不调用" in prompt, (
        f"synthesizer prompt missing no-business-tool clause: {prompt[:200]}"
    )


# 功能：rag 的 system_prompt 必须明确"引用"约束
# 设计：plan §3 明确要求 RAG 助手"引用必须保留"；system_prompt 漏写会让模型自由发挥丢引用
def test_rag_prompt_states_citation_required() -> None:
    profile = AgentProfileLoader().load("rag")
    assert profile is not None
    assert "引用" in profile.system_prompt, (
        f"rag prompt missing '引用' clause: {profile.system_prompt[:200]}"
    )


# ─────────────────────────── AgentProfile dataclass 与 TOML 解析一致性 ───────────────────────────


# 功能：业务 Profile 解析后类型是 AgentProfile（loader 返回类型契约）
# 设计：直接断言 isinstance；防止有人把 load() 改成返回 dict 等破坏类型契约
@pytest.mark.parametrize("name", BUSINESS_PROFILE_NAMES)
def test_business_profile_returns_agent_profile_instance(name: str) -> None:
    profile = AgentProfileLoader().load(name)
    assert isinstance(profile, AgentProfile)
