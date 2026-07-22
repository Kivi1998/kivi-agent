from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# 检测 bash 命令是否操作 cwd 之外路径的正则规则列表（强制触发 ASK，不可被 allow_patterns 绕过）
OUTSIDE_CWD_HEURISTICS: list[str] = [
    r"(^|\s)/[^\s]",              # absolute path
    r"(^|\s)~",                   # tilde home
    r"(^|\s)\.\.(/|$|\s)",        # parent traversal
    r"\$\{?HOME\b",               # $HOME variable
    r"\$\{?PWD\b",                # $PWD variable
    r"(^|\s|;|&&|\|\|)cd(\s|$)",  # explicit cd
]

_OUTSIDE_CWD_RE: list[re.Pattern[str]] = [re.compile(p) for p in OUTSIDE_CWD_HEURISTICS]


# 判断 bash 命令是否命中 outside-cwd 启发式规则
def matches_outside_cwd(command: str) -> bool:
    return any(pat.search(command) for pat in _OUTSIDE_CWD_RE)


@dataclass
class ToolPolicy:
    default: PermissionDecision
    allow_patterns: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)


DEFAULT_POLICIES: dict[str, ToolPolicy] = {
    "bash":       ToolPolicy(default=PermissionDecision.ASK),
    "write_file": ToolPolicy(default=PermissionDecision.ASK),
    "read_file":  ToolPolicy(default=PermissionDecision.ALLOW),
    "list_dir":   ToolPolicy(default=PermissionDecision.ALLOW),
    "note_save":  ToolPolicy(default=PermissionDecision.ALLOW),
    # glob（agent: minimal-loop）
    "glob":       ToolPolicy(default=PermissionDecision.ALLOW),
    # grep（agent: minimal-loop）
    "grep":       ToolPolicy(default=PermissionDecision.ALLOW),
    # edit_file（agent: minimal-loop）
    "edit_file":  ToolPolicy(default=PermissionDecision.ASK),
    # diff（agent: minimal-loop）
    "diff":       ToolPolicy(default=PermissionDecision.ALLOW),
    # enter_worktree（agent: minimal-loop）
    "enter_worktree": ToolPolicy(default=PermissionDecision.ALLOW),
    # exit_worktree（agent: minimal-loop）
    "exit_worktree":  ToolPolicy(default=PermissionDecision.ASK),
    # exit_plan_mode（agent: package-d）
    "exit_plan_mode": ToolPolicy(default=PermissionDecision.ALLOW),
    # team_create（agent: package-f）：会真实起多个后台 LLM 调用，产生成本，默认需要审批
    "team_create": ToolPolicy(default=PermissionDecision.ASK),
    # team_message（agent: package-f）：纯文本消息传递，低风险
    "team_message": ToolPolicy(default=PermissionDecision.ALLOW),
    # team_status（agent: package-f）：只读查询，无副作用
    "team_status": ToolPolicy(default=PermissionDecision.ALLOW),
    # tool_search（agent: package-b）：只读，按关键词发现已注册工具
    "tool_search": ToolPolicy(default=PermissionDecision.ALLOW),
    # ask_user（agent: package-c）：向用户提问会真正挂起 LLM 调用，需审批
    "ask_user": ToolPolicy(default=PermissionDecision.ASK),
    # rewind_file（agent: package-c）：覆盖文件内容，破坏性操作需审批
    "rewind_file": ToolPolicy(default=PermissionDecision.ASK),
}

# 未在 DEFAULT_POLICIES 中登记的工具的兜底策略
_UNKNOWN_TOOL_DEFAULT = PermissionDecision.ASK

# bash 参数中展示用的关键字段映射
_PREVIEW_KEY: dict[str, str] = {
    "bash":       "command",
    "read_file":  "path",
    "write_file": "path",
    "list_dir":   "path",
    "note_save":  "content",
    # edit_file（agent: minimal-loop）：审批卡片展示被编辑的文件路径
    "edit_file":  "path",
    # enter_worktree（agent: minimal-loop）：审批卡片展示任务名
    "enter_worktree": "name",
    # exit_worktree（agent: minimal-loop）：审批卡片展示工作树路径
    "exit_worktree":  "path",
    # ask_user（agent: package-c）：审批卡片展示问题文本
    "ask_user":   "question",
    # rewind_file（agent: package-c）：审批卡片展示被还原的文件路径
    "rewind_file": "path",
}
_PREVIEW_MAX = 60


# 为权限审批事件生成人类可读的参数摘要
def param_preview(tool_name: str, params: dict[str, Any]) -> str:
    key = _PREVIEW_KEY.get(tool_name)
    if key and key in params:
        val = str(params[key])
        if len(val) > _PREVIEW_MAX:
            val = val[:_PREVIEW_MAX] + "…"
        return f"{key}={val!r}"
    snippet = str(params)
    return snippet[:_PREVIEW_MAX] if len(snippet) > _PREVIEW_MAX else snippet


# 对工具 + 参数执行 4 层静态策略评估，返回 ALLOW/DENY/ASK
def evaluate(
    tool_name: str,
    params: dict[str, Any],
    policy: ToolPolicy | None = None,
) -> PermissionDecision:
    if policy is None:
        policy = DEFAULT_POLICIES.get(tool_name)

    if policy is None:
        return _UNKNOWN_TOOL_DEFAULT

    command = str(params.get("command", "")) if tool_name == "bash" else ""

    # Tier 1: deny_patterns (bash only)
    if command:
        for pat in policy.deny_patterns:
            if re.search(pat, command):
                return PermissionDecision.DENY

    # Tier 2: OUTSIDE_CWD_HEURISTICS — forced ASK, not bypassable
    if command and matches_outside_cwd(command):
        return PermissionDecision.ASK

    # Tier 3: allow_patterns (bash only)
    if command:
        for pat in policy.allow_patterns:
            if re.search(pat, command):
                return PermissionDecision.ALLOW

    # Tier 4: tool default
    return policy.default
