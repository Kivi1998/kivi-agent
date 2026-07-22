# kamaAgent 包G：技能分发 + MCP 扩展 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给已有的 `SkillLoader`（只会从本地 `.kivi/skills/`/`~/.kivi/skills/` 加载）加关键词搜索和从 Git 仓库安装的能力；给已有的 `McpClient`（只支持 stdio/tcp）加 HTTP 传输；给 `McpServerConfig.env` 加密钥引用语法，避免明文密钥写进配置文件。

**Architecture:** 四个改动互相独立，不共享新增基础设施，直接在现有模块上做局部扩展——`SkillLoader` 加方法、`core/skills/` 加一个新文件、`McpClient` 加一个新的 transport 分支、`core/mcp/` 加一个新的小工具函数。不引入 mewcode 的签名校验机制（YAGNI，见 Global Constraints）。

**Tech Stack:** Python 3.12、pydantic v2、pytest + pytest-asyncio、uv、`httpx[socks]`（已是依赖）、Git CLI（技能安装用 `git clone`，不重新实现 GitHub Contents API 递归下载）。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **技能安装用 `git clone`，不用 GitHub Contents API 递归下载**——mewcode 那套实现是为了不依赖用户本机装 git，但 Kama 本来就依赖 git（工作树功能），没必要重新发明一遍下载逻辑，`git clone --depth 1` 更简单、支持任意 git host 不只是 GitHub。
- **不做签名校验**——mewcode 本身也没做，只有体积/路径限制；个人场景下技能来源可信度由用户自己把关，加签名校验是过度工程。
- 涉及路径的操作必须复用已有的目录穿越防护模式（技能名做 slug 化处理，不允许 `..`）。

---

### Task G1: Skill 关键词搜索

**Files:**
- Modify: `src/kivi_agent/core/skills/loader.py`
- Test: `tests/unit/test_skill_loader.py`（追加用例）

**Interfaces:**
- Consumes: 已有 `SkillLoader.list_all_skills()`
- Produces: `SkillLoader.search(query: str, limit: int = 5) -> list[Skill]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_skill_loader.py 追加
# 功能：验证按关键词能搜到名字或描述里含该词的 skill，且结果按匹配度排序（名字命中优先于描述命中）
# 设计：用两个内建 skill 举例（假设 review.md 描述含"审查"、summarize.md 描述含"摘要"），
#      实际测试改用临时目录写两个假 skill 文件，避免依赖内建 skill 内容随时间变化
def test_search_finds_by_name_and_description(tmp_path, monkeypatch) -> None:
    skills_dir = tmp_path / ".kivi" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "code-review.md").write_text(
        "---\nname: code-review\ndescription: 审查代码改动\n---\n审查 prompt 正文"
    )
    (skills_dir / "summarize.md").write_text(
        "---\nname: summarize\ndescription: 生成摘要\n---\n摘要 prompt 正文"
    )
    monkeypatch.chdir(tmp_path)

    loader = SkillLoader()
    results = loader.search("审查")
    assert len(results) == 1
    assert results[0].name == "code-review"


# 功能：验证搜索结果数量受 limit 参数限制
# 设计：写 3 个都匹配同一关键词的 skill，limit=2 时断言只返回 2 个
def test_search_respects_limit(tmp_path, monkeypatch) -> None:
    skills_dir = tmp_path / ".kivi" / "skills"
    skills_dir.mkdir(parents=True)
    for i in range(3):
        (skills_dir / f"tool-{i}.md").write_text(
            f"---\nname: tool-{i}\ndescription: 工具相关技能 {i}\n---\n正文"
        )
    monkeypatch.chdir(tmp_path)

    loader = SkillLoader()
    results = loader.search("工具", limit=2)
    assert len(results) == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_skill_loader.py -k search -v`
Expected: FAIL（`AttributeError: 'SkillLoader' object has no attribute 'search'`）

- [ ] **Step 3: 实现**

在 `core/skills/loader.py` 的 `class SkillLoader` 里加方法：

```python
    # 按关键词搜索 skill：名字命中权重高于描述命中，按分数降序返回最多 limit 个
    def search(self, query: str, limit: int = 5) -> list[Skill]:
        q = query.strip().lower()
        if not q:
            return []
        scored: list[tuple[int, Skill]] = []
        for skill in self.list_all_skills():
            score = 0
            if q in skill.name.lower():
                score += 10
            if q in skill.description.lower():
                score += 5
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [skill for _, skill in scored[:limit]]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_skill_loader.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git add src/kivi_agent/core/skills/loader.py tests/unit/test_skill_loader.py
git commit -m "feat: SkillLoader 加关键词搜索"
```

---

### Task G2: Skill 安装（git clone）

**Files:**
- Create: `src/kivi_agent/core/skills/install.py`
- Test: `tests/unit/test_skill_install.py`

**Interfaces:**
- Produces: `async def install_skill(git_url: str, name: str, dest_root: Path) -> Path`（返回安装后的技能目录路径；失败抛 `SkillInstallError`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_skill_install.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kivi_agent.core.skills.install import SkillInstallError, install_skill


# 用本地临时 git 仓库模拟"远程技能仓库"，避免测试依赖真实网络
@pytest.fixture
def fake_skill_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "SKILL.md").write_text("---\nname: demo-skill\ndescription: 演示\n---\n正文")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    return repo


# 功能：验证从含 SKILL.md 的仓库安装成功后，目标目录下能找到 SKILL.md
# 设计：用本地仓库路径当 git_url（git clone 支持本地路径），断言安装后文件确实落地在 dest_root/<name>/
async def test_install_skill_copies_skill_md(fake_skill_repo: Path, tmp_path: Path) -> None:
    dest_root = tmp_path / "installed"
    result_path = await install_skill(str(fake_skill_repo), "demo-skill", dest_root)
    assert (result_path / "SKILL.md").exists()
    assert result_path == dest_root / "demo-skill"


# 功能：验证仓库里没有 SKILL.md 时安装失败并抛出明确错误，不留下部分文件
# 设计：clone 一个不含 SKILL.md 的仓库，断言抛 SkillInstallError 且目标目录未被创建（原子性）
async def test_install_skill_rejects_repo_without_skill_md(tmp_path: Path) -> None:
    repo = tmp_path / "bad-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("no skill here")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)

    dest_root = tmp_path / "installed2"
    with pytest.raises(SkillInstallError):
        await install_skill(str(repo), "bad-skill", dest_root)
    assert not (dest_root / "bad-skill").exists()


# 功能：验证技能名包含路径穿越字符（如 ".."）时被拒绝，不执行任何 git 操作
# 设计：与仓库其它工具一致的安全边界，防止恶意 name 参数把文件装到目标目录之外
async def test_install_skill_rejects_path_traversal_name(tmp_path: Path) -> None:
    with pytest.raises(SkillInstallError):
        await install_skill("https://example.com/repo.git", "../escape", tmp_path)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_skill_install.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/skills/install.py
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path


class SkillInstallError(Exception):
    pass


# 从 git 仓库安装一个技能：clone 到临时目录，校验含 SKILL.md，原子 rename 到目标目录
async def install_skill(git_url: str, name: str, dest_root: Path) -> Path:
    if ".." in Path(name).parts or "/" in name:
        raise SkillInstallError(f"invalid skill name: {name}")

    dest = dest_root / name
    if dest.exists():
        raise SkillInstallError(f"skill already installed: {name}")

    with tempfile.TemporaryDirectory() as tmp:
        clone_path = Path(tmp) / "clone"
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", git_url, str(clone_path),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise SkillInstallError(f"git clone failed: {stderr.decode(errors='replace')}")

        skill_md = clone_path / "SKILL.md"
        if not skill_md.exists():
            raise SkillInstallError(f"repository does not contain SKILL.md: {git_url}")

        dest_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(clone_path), str(dest))

    return dest
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_skill_install.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/skills/install.py tests/unit/test_skill_install.py
git commit -m "feat: 新增 Skill 安装能力，从 git 仓库 clone 并校验 SKILL.md"
```

---

### Task G3: MCP HTTP 传输

**Files:**
- Modify: `src/kivi_agent/core/mcp/client.py`
- Modify: `src/kivi_agent/core/mcp/server.py`
- Modify: `src/kivi_agent/core/config.py`
- Test: `tests/unit/test_mcp_client.py`（追加用例，若无此文件则新建）

**Interfaces:**
- Produces: `McpClient.connect_http(url: str, headers: dict[str, str] | None = None) -> None`
- Modifies: `McpServerConfig.transport` 新增 `"http"` 取值；新增字段 `url: str = ""`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_mcp_client.py（若已存在同名测试文件则追加，此处假设新建）
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from kivi_agent.core.mcp.client import McpClient


# 功能：验证 connect_http 用 httpx 向指定 URL 发 initialize 请求完成握手，不走 stdio/tcp 那套行读取
# 设计：mock httpx.AsyncClient.post 返回一个符合 JSON-RPC 格式的 initialize 响应，
#      断言 connect_http 正常完成不抛异常，且后续 list_tools 也走同一个 HTTP POST 路径
async def test_connect_http_completes_handshake() -> None:
    client = McpClient()

    async def _fake_post(url, json, headers=None, **kwargs):
        method = json.get("method")
        response = AsyncMock()
        if method == "initialize":
            response.json = lambda: {"jsonrpc": "2.0", "id": json["id"], "result": {}}
        elif method == "tools/list":
            response.json = lambda: {
                "jsonrpc": "2.0", "id": json["id"],
                "result": {"tools": [{"name": "echo", "description": "回显", "inputSchema": {}}]},
            }
        else:
            response.json = lambda: {"jsonrpc": "2.0", "id": json["id"], "result": {}}
        response.raise_for_status = lambda: None
        return response

    with patch("httpx.AsyncClient.post", new=_fake_post):
        await client.connect_http("http://fake-mcp-server/rpc")
        tools = await client.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "echo"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_mcp_client.py -k http -v`
Expected: FAIL（`AttributeError: 'McpClient' object has no attribute 'connect_http'`）

- [ ] **Step 3: 实现**

在 `core/mcp/client.py` 顶部加 `import httpx`。`class McpClient.__init__` 里加：

```python
        self._http_url: str | None = None
        self._http_headers: dict[str, str] = {}
        self._http_client: httpx.AsyncClient | None = None
```

新增方法（放在 `connect_tcp` 之后）：

```python
    # 通过 HTTP POST 连接 MCP server（streamable HTTP transport）并完成 initialize 握手
    async def connect_http(self, url: str, headers: dict[str, str] | None = None) -> None:
        self._http_url = url
        self._http_headers = headers or {}
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._transport = "http"
        await self._initialize()
```

改造 `_call()`，在方法开头加 HTTP 分支（HTTP 是请求-响应式，不走 `_write_line`/`_read_line` 那套持久流读取）：

```python
    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        req_id = self._id
        request = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}

        if self._transport == "http":
            assert self._http_client is not None and self._http_url is not None
            response = await self._http_client.post(
                self._http_url, json=request, headers=self._http_headers,
            )
            response.raise_for_status()
            msg = response.json()
            if "error" in msg:
                err = msg["error"]
                raise McpToolError(f"{err.get('message', str(err))} (code={err.get('code')})")
            result: dict[str, Any] = msg.get("result", {})
            return result

        req_id_str = str(req_id)
        async with self._lock:
            # ...（原有 stdio/tcp 逻辑不变，从这里往下保持原样）
```

`close()` 方法里加 HTTP 分支：

```python
        elif self._transport == "http":
            if self._http_client is not None:
                await self._http_client.aclose()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_mcp_client.py -v`
Expected: PASS

- [ ] **Step 5: 接入配置和 McpServerManager**

`core/config.py::McpServerConfig` 加字段：

```python
    url: str = ""  # http 专用
```

`core/mcp/server.py::McpServerManager._connect()` 加分支：

```python
        elif cfg.transport == "http":
            if not cfg.url:
                raise ValueError(f"mcp server '{cfg.name}': http transport requires 'url'")
            await client.connect_http(cfg.url, cfg.env or None)  # env 复用作 HTTP headers，见 Task G4
```

（`cfg.env` 复用作 HTTP headers 传递，是否合适取决于 Task G4 的密钥引用设计——若 Task G4 已经把 `env` 定位为"通用键值对，stdio 场景当环境变量、http 场景当 header"，这里就是自然的复用；实现时对照 G4 的最终字段设计确认一致，若冲突则改用单独的 `headers: dict[str, str]` 字段。）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/mcp/client.py src/kivi_agent/core/mcp/server.py \
        src/kivi_agent/core/config.py tests/unit/test_mcp_client.py
git commit -m "feat: MCP 客户端新增 HTTP 传输支持"
```

---

### Task G4: MCP 密钥引用（避免明文密钥落盘）

**Files:**
- Create: `src/kivi_agent/core/mcp/secrets.py`
- Modify: `src/kivi_agent/core/mcp/server.py`
- Test: `tests/unit/test_mcp_secrets.py`

**Interfaces:**
- Produces: `def resolve_secret_refs(env: dict[str, str]) -> dict[str, str]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_mcp_secrets.py
from __future__ import annotations

from kivi_agent.core.mcp.secrets import resolve_secret_refs


# 功能：验证形如 ${SECRET:NAME} 的值被替换成对应环境变量的实际值
# 设计：设置一个环境变量，构造引用它的 env 字典，断言解析后的值就是环境变量的真实值，
#      而不是字面量 "${SECRET:NAME}" 字符串
def test_resolve_secret_refs_substitutes_env_var(monkeypatch) -> None:
    monkeypatch.setenv("MY_API_KEY", "sk-real-secret-value")
    env = {"API_KEY": "${SECRET:MY_API_KEY}", "PLAIN": "not-a-secret"}
    resolved = resolve_secret_refs(env)
    assert resolved["API_KEY"] == "sk-real-secret-value"
    assert resolved["PLAIN"] == "not-a-secret"


# 功能：验证引用了未设置的环境变量时，解析结果为空字符串而不是抛异常
# 设计：连接失败应该交给 server 因为凭据为空而报错，而不是在这一层直接中断——
#      保持和现有 mcp start_all() "单个 server 失败只记日志跳过"的容错风格一致
def test_resolve_secret_refs_missing_env_var_becomes_empty(monkeypatch) -> None:
    monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
    env = {"API_KEY": "${SECRET:NONEXISTENT_KEY}"}
    resolved = resolve_secret_refs(env)
    assert resolved["API_KEY"] == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_mcp_secrets.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/mcp/secrets.py
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

_SECRET_REF_RE = re.compile(r"^\$\{SECRET:([A-Za-z_][A-Za-z0-9_]*)\}$")


# 把形如 "${SECRET:NAME}" 的值替换为对应环境变量的真实值；未设置的环境变量替换为空字符串
def resolve_secret_refs(env: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in env.items():
        match = _SECRET_REF_RE.match(value)
        if match is None:
            resolved[key] = value
            continue
        var_name = match.group(1)
        actual = os.environ.get(var_name)
        if actual is None:
            log.warning("mcp secret reference unresolved: %s -> $%s not set", key, var_name)
            actual = ""
        resolved[key] = actual
    return resolved
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_mcp_secrets.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 接入 McpServerManager**

在 `core/mcp/server.py::_connect()` 方法开头加：

```python
    async def _connect(self, cfg: McpServerConfig) -> McpClient:
        from kivi_agent.core.mcp.secrets import resolve_secret_refs

        resolved_env = resolve_secret_refs(cfg.env) if cfg.env else {}
        client = McpClient()
        if cfg.transport == "stdio":
            if not cfg.command:
                raise ValueError(f"mcp server '{cfg.name}': stdio transport requires 'command'")
            await client.connect_stdio(cfg.command, cfg.args, resolved_env or None)
        elif cfg.transport == "tcp":
            await client.connect_tcp(cfg.host, cfg.port)
        elif cfg.transport == "http":
            if not cfg.url:
                raise ValueError(f"mcp server '{cfg.name}': http transport requires 'url'")
            await client.connect_http(cfg.url, resolved_env or None)
        else:
            raise ValueError(f"mcp server '{cfg.name}': unknown transport '{cfg.transport}'")
        return client
```

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/mcp/secrets.py src/kivi_agent/core/mcp/server.py tests/unit/test_mcp_secrets.py
git commit -m "feat: MCP env 支持 \${SECRET:NAME} 引用语法，避免明文密钥写入配置文件"
```

---

## Self-Review Notes

- **覆盖范围**：G1-G2 覆盖 M38（技能搜索，已有加载机制上扩展）+ M37（技能安装，简化为 git clone）；G3-G4 覆盖 M39（MCP HTTP 传输）+ M40（MCP 密钥引用）。
- **有意排除**：技能签名校验（mewcode 本身也没有）、SSE 独立传输分支（streamable HTTP 已经是 MCP 规范里 stdio/HTTP 二选一的现代方案，不需要额外单独实现 SSE）。
- **类型一致性**：`McpClient._call()` 的 HTTP 分支和原有 stdio/tcp 分支共用同一个返回类型 `dict[str, Any]` 和同一个 `McpToolError` 异常类型，`list_tools()`/`call_tool()` 两个上层方法不需要感知底层走的是哪种 transport，改动完全局部于 `_call()`/`connect_*()`/`close()` 三个方法内部。
