"""Skills 2.0 数据结构：SkillDefinition。

契约冻结 v1 + 整合方案 §7.2：双模式（command_mode + tool_mode）+ 5 分类
+ 渐进式披露相关字段（runtime_context_keys / references / scripts）。

与旧 `Skill` dataclass 字段完全兼容（name / description / allowed_tools /
system_prompt_template）；新增字段全部带默认值，旧调用方可零修改实例化。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# 合法的 Skill 分类：与 aigroup 5 类对齐（v1 §1 Tool 命名侧正交）
SkillCategory = Literal["general", "rag", "web_search", "database", "tool"]


# ───────────────────────── 脚本执行描述（嵌套结构） ─────────────────────────


@dataclass
class ScriptSpec:
    """单个脚本条目：相对路径 + 解释器。

    B 阶段：保持简单 dict-like 形态（path / interpreter 两键），
    避免引入 Pydantic 给 dataclass 路径加复杂度。后续若需要 type/
    timeout 字段，按 v2 契约再升级为 Pydantic model。
    """

    path: str                # 相对 skill_dir 的路径，如 "scripts/main.py"
    interpreter: str = "python"  # python | node | bash

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "interpreter": self.interpreter}


# ───────────────────────── SkillDefinition 主类 ─────────────────────────


@dataclass
class SkillDefinition:
    """Skill 元数据 + 双模式开关（Skills 2.0 契约）。

    启动时只读 frontmatter 构建本对象；正文（SKILL.md body）由
    SkillContentReader 延迟到调用时读，避免大文件过早占内存。
    """

    # ── 标识 ──
    name: str                                          # 主名（同时是 tool_name 缺省值）
    description: str = ""                              # command 弹窗 + tool 选择共同使用

    # ── 内容（启动时 frontmatter，正文延迟读） ──
    system_prompt_template: str = ""                   # SKILL.md 正文（兼容旧 Skill 字段）
    allowed_tools: list[str] = field(default_factory=list)  # command_mode 工具白名单

    # ── 模式开关（双模式默认全开） ──
    command_mode: bool = True                          # /skill 显式触发（kivi 旧行为）
    tool_mode: bool = True                             # 注册成 Tool，模型自主调用

    # ── 分类（v1 §1 与 Tool 命名正交） ──
    category: SkillCategory = "general"

    # ── 渐进式披露 ──
    runtime_context_keys: list[str] = field(default_factory=list)  # 从 RunContext 注入的字段名
    references: list[str] = field(default_factory=list)             # references/ 下相对路径
    scripts: list[dict[str, str]] = field(default_factory=list)     # 每项含 path + interpreter

    # ── 源码信息 ──
    source: str = "builtin"                            # builtin | user | project
    skill_dir: str = ""                                # 绝对路径字符串（跨平台可序列化）

    # ── 元数据（frontmatter 但未结构化的部分，调试用） ──
    raw_frontmatter: dict[str, object] = field(default_factory=dict)

    # ────── 便捷属性 ──────

    @property
    def has_references(self) -> bool:
        return len(self.references) > 0

    @property
    def has_scripts(self) -> bool:
        return len(self.scripts) > 0

    @property
    def primary_script(self) -> dict[str, str] | None:
        """返回第一个脚本（顺序在 frontmatter 决定），无则 None。"""
        return self.scripts[0] if self.scripts else None
