"""Skills 2.0 数据结构：SkillDefinition。

契约冻结 v1 + 整合方案 §7.2：双模式（command_mode + tool_mode）+ 5 分类
+ 渐进式披露相关字段（runtime_context_keys / references / scripts）。

与旧 `Skill` dataclass 字段完全兼容（name / description / allowed_tools /
system_prompt_template）；新增字段全部带默认值，旧调用方可零修改实例化。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
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

    # ────── Frontmatter 解析（YAML-lite，与 core/skills/loader.py 风格一致） ──────

    # 从 .md 文件解析 SkillDefinition（兼容 Skills 2.0 新字段；未声明则用默认值）
    @classmethod
    def from_file(cls, path: Path, *, source: str = "builtin") -> SkillDefinition:
        text = path.read_text(encoding="utf-8")
        name = path.stem
        description = ""
        allowed_tools: list[str] = []
        body = text

        category: SkillCategory = "general"
        command_mode = True
        tool_mode = True
        runtime_context_keys: list[str] = []
        references: list[str] = []
        scripts: list[dict[str, str]] = []
        raw: dict[str, object] = {}

        m = _FRONTMATTER_RE.match(text)
        if m:
            front = m.group(1)
            body = text[m.end():]
            lines = front.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                stripped = line.strip()
                if not stripped:
                    i += 1
                    continue
                # name / description 解析
                if stripped.startswith("name:"):
                    name = _scalar(stripped, "name:")
                elif stripped.startswith("description:"):
                    val = stripped[len("description:"):].strip()
                    if val in (">", "|"):
                        fold = val == ">"
                        parts: list[str] = []
                        i += 1
                        while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("\t")):
                            parts.append(lines[i].strip())
                            i += 1
                        description = (" ".join(parts) if fold else "\n".join(parts)).strip()
                        continue
                    description = val.strip('"').strip("'")
                # 标量字段
                elif stripped.startswith("category:"):
                    category = _scalar(stripped, "category:")  # type: ignore[assignment]
                elif stripped.startswith("command_mode:"):
                    command_mode = _parse_bool(_scalar(stripped, "command_mode:"))
                elif stripped.startswith("tool_mode:"):
                    tool_mode = _parse_bool(_scalar(stripped, "tool_mode:"))
                # 列表字段：解析 - 子项
                elif stripped.endswith(":"):
                    key = stripped[:-1].strip()
                    i += 1
                    items: list[str] = []
                    while i < len(lines) and lines[i].lstrip().startswith("- "):
                        items.append(lines[i].lstrip()[2:].strip())
                        i += 1
                    if key == "allowed_tools":
                        allowed_tools = items
                    elif key == "runtime_context_keys":
                        runtime_context_keys = items
                    elif key == "references":
                        references = items
                    elif key == "scripts":
                        scripts = _parse_scripts_list(items)
                    else:
                        raw[key] = items
                    continue
                i += 1

        return cls(
            name=name,
            description=description,
            system_prompt_template=body.strip(),
            allowed_tools=allowed_tools,
            command_mode=command_mode,
            tool_mode=tool_mode,
            category=category,
            runtime_context_keys=runtime_context_keys,
            references=references,
            scripts=scripts,
            source=source,
            skill_dir=str(path.parent.resolve()),
            raw_frontmatter=raw,
        )


# ───────────────────────── Frontmatter 内部辅助 ─────────────────────────


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# 解析单行标量（剥引号）
def _scalar(line: str, key: str) -> str:
    return line[len(key):].strip().strip('"').strip("'")


# 解析 bool（"true"/"false"，大小写不敏感）
def _parse_bool(text: str) -> bool:
    return text.strip().lower() == "true"


# 解析 scripts 列表（每行形如 "{path: scripts/main.py, interpreter: python}"）
def _parse_scripts_list(items: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        # 去掉外层大括号（若有）
        cleaned = item.strip().strip("{}")
        entry: dict[str, str] = {}
        for part in cleaned.split(","):
            part = part.strip()
            if ":" in part:
                k, v = part.split(":", 1)
                entry[k.strip()] = v.strip().strip('"').strip("'")
        if "path" in entry:
            entry.setdefault("interpreter", "python")
            out.append(entry)
    return out
