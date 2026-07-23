from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from kivi_agent.core.permissions.modes import PermissionMode


@dataclass
class AgentProfile:
    name: str
    description: str = ""
    system_prompt: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    model: str = ""
    # v1 §3 扩展字段：5 个新字段，全部用 dataclass 默认值保持向后兼容
    max_steps: int = 20
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    result_schema: dict[str, object] | None = None
    concurrency_group: str = "default"
    category: Literal["read", "write", "command", "other"] = "other"


# 按两级优先级（项目本地 > 用户全局 > 内建）查找并解析角色配置
class AgentProfileLoader:
    _BUILTIN_DIR = Path(__file__).parent / "builtin"

    # 查找指定角色配置；未找到返回 None
    def load(self, name: str) -> AgentProfile | None:
        for path in self._search_paths(name):
            if path.exists():
                try:
                    return self._parse(path, name)
                except Exception:
                    return None
        return None

    # 返回 [项目本地, 用户全局, 内建, 内建业务子目录] 路径；load() 返回第一个存在的，项目本地优先级最高
    def _search_paths(self, name: str) -> list[Path]:
        # 路径遍历保护：业务子目录名硬编码为 "business"，不接受外部输入
        builtin_business = self._BUILTIN_DIR / "business" / f"{name}.toml"
        if ".." in builtin_business.parts:
            raise ValueError("invalid profile path")
        builtin = self._BUILTIN_DIR / f"{name}.toml"
        global_ = Path("~/.kivi/agents").expanduser() / f"{name}.toml"
        local = Path(".kivi/agents") / f"{name}.toml"
        return [local, global_, builtin, builtin_business]

    # 解析 TOML 角色配置文件（含 v1 §3 5 个扩展字段）
    def _parse(self, path: Path, name: str) -> AgentProfile:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        agent = data.get("agent", {})
        # permission_mode 字符串转 PermissionMode 枚举；缺省时 dataclass 默认值接管
        raw_mode = agent.get("permission_mode", PermissionMode.DEFAULT)
        if isinstance(raw_mode, PermissionMode):
            mode = raw_mode
        else:
            mode = PermissionMode(str(raw_mode))
        return AgentProfile(
            name=name,
            description=agent.get("description", ""),
            system_prompt=agent.get("system_prompt", "").strip(),
            allowed_tools=agent.get("allowed_tools", []),
            model=agent.get("model", ""),
            max_steps=agent.get("max_steps", 20),
            permission_mode=mode,
            result_schema=agent.get("result_schema"),
            concurrency_group=agent.get("concurrency_group", "default"),
            category=agent.get("category", "other"),
        )
