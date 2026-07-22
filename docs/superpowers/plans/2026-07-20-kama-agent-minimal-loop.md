# kamaAgent 个人可执行最小闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 kivi-agent（stage/s7）基础上，迁移 mewcode 的四类关键能力（真实编程工具、多模型 Provider、Git 工作树隔离、命令沙箱），跑通《kamaAgent 企业 Agent 平台整合方案》第 21 章"首轮落地建议"描述的最小闭环：用户在 TUI 发起一个真实代码修改任务 → Agent 用搜索/精确编辑/差异工具完成修改 → 修改发生在独立 Git 工作树内 → 高风险命令经沙箱执行并触发审批 → 用户看差异决定接受。

**Architecture:** 不新建仓库、不引入服务化/多前端/企业治理（那些是团队级任务，不适合个人执行）。所有新增能力都以 kivi-agent 现有扩展点接入：新工具继承 `core/tools/builtin/` 下的 `BaseTool`，新 Provider 实现 `core/llm/base.py` 的 `LLMProvider` Protocol，工作树与沙箱各自成一个新包（`core/workspace/`、`core/sandbox/`），最终都在 `core/runner.py::_build_registry()` 注册、在 `core/permissions/policy.py::DEFAULT_POLICIES` 登记权限策略。mewcode 没有 LICENSE 文件，因此只迁移设计思路、在 kivi-agent 里用自己的代码风格重写，不直接复制 mewcode 源码。

**Tech Stack:** Python 3.12、pydantic v2、uv（包管理）、pytest + pytest-asyncio、Anthropic SDK（已有）、openai SDK（新增，用于 OpenAI 兼容 Provider）、Git CLI（工作树）、`sandbox-exec`（macOS 沙箱）/ `bwrap`（Linux 沙箱，需系统预装 bubblewrap）。

## Global Constraints

- 不新建仓库：在现有 `Kama/kivi-agent` 仓库基于 `stage/s7` 建分支 `feat/kivi-agent-minimal-loop`。
- mewcode 无 LICENSE 文件：只迁移算法/架构思路，所有代码在 kivi-agent 中独立实现，禁止逐段复制 mewcode 源码。
- 每个函数定义上方必须有一行中文注释说明该函数做什么（仓库 `CLAUDE.md` 强制要求）。
- 每个测试函数上方必须有两行中文注释：`# 功能：` 一句话说明测什么；`# 设计：` 一句话说明为什么这样测（覆盖什么边界/为什么选这种断言）。
- 新工具必须在 `core/tools/builtin/` 下新建文件，继承 `core.tools.base.BaseTool`，实现 `name`、`description`、`input_schema`、`params_model`（pydantic `BaseModel`，`model_config = ConfigDict(extra="ignore")`）、`async def invoke(self, params: dict[str, object]) -> ToolResult`。
- 新工具必须在 `core/runner.py::_build_registry()` 中显式 `registry.register(...)`，并在 `core/permissions/policy.py::DEFAULT_POLICIES` 中登记默认策略（否则兜底为 `ASK`，不算错但要显式声明意图）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量：`uv run pytest tests/unit -v`；lint：`uv run ruff check src tests`；类型检查：`uv run mypy src`。
- 涉及路径的工具必须复用已有的目录穿越防护写法（`if ".." in Path(path_str).parts: raise PermissionError(...)`），保持和 `read_file.py`/`write_file.py` 一致的安全边界。

---

### Task 1: 建立开发分支并记录 mewcode 迁移的许可边界

**Files:**
- Create: `docs/迁移记录/mewcode迁移许可说明.md`

**Interfaces:**
- 无代码接口，纯治理动作，为后续所有任务提供"只迁移思路、不复制源码"的书面依据。

- [ ] **Step 1: 从 stage/s7 建分支**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git checkout stage/s7
git pull origin stage/s7
git checkout -b feat/kivi-agent-minimal-loop
```

- [ ] **Step 2: 写许可说明文档**

```markdown
# mewcode 迁移许可说明

- mewcode（`/Users/kivi/Documents/agent系统/mewcode`）根目录未发现 LICENSE 文件，来源和授权条款不明确。
- 因此本次迁移（工作分支 `feat/kivi-agent-minimal-loop`）只参考 mewcode 的设计思路和公开算法（如 glob/grep 的过滤策略、edit_file 的唯一匹配替换逻辑、diff 的展示格式、Git 工作树生命周期管理、macOS/Linux 沙箱的系统机制选型），所有代码在 kivi-agent 仓库中用自己的类型系统、工具基类和错误处理约定独立实现。
- 不直接复制、粘贴 mewcode 的任何源码文件。
- 如后续需要更大范围迁移（企业级整合方案中的 M01~M44），必须先取得 mewcode 明确的许可声明或改为完全独立重写。
```

- [ ] **Step 3: 提交**

```bash
mkdir -p docs/迁移记录
git add docs/迁移记录/mewcode迁移许可说明.md
git commit -m "docs: 记录 mewcode 迁移的许可边界"
```

---

### Task 2: GlobTool — 文件名模式搜索

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/_fs_filters.py`
- Create: `src/kivi_agent/core/tools/builtin/glob_tool.py`
- Test: `tests/unit/test_glob_tool.py`
- Modify: `src/kivi_agent/core/runner.py`（`_build_registry` 内注册）
- Modify: `src/kivi_agent/core/permissions/policy.py`（`DEFAULT_POLICIES` 登记）

**Interfaces:**
- Produces: `SKIP_DIRS: frozenset[str]`（`_fs_filters.py`，后续 `grep_tool.py` 复用）
- Produces: `class GlobTool(BaseTool)`，`name = "glob"`

- [ ] **Step 1: 写共享过滤常量**

```python
# src/kivi_agent/core/tools/builtin/_fs_filters.py
from __future__ import annotations

# 搜索类工具（glob/grep）统一跳过的目录名
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache"}
)


# 判断路径是否落在需要跳过的目录内（任一层级命中即跳过）
def is_skipped(path_parts: tuple[str, ...]) -> bool:
    return any(part in SKIP_DIRS for part in path_parts)
```

- [ ] **Step 2: 写失败测试**

```python
# tests/unit/test_glob_tool.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.tools.builtin.glob_tool import GlobTool


# 功能：验证按 *.py 模式能搜到匹配文件，按 mtime 倒序排列
# 设计：写两个文件并控制 mtime 顺序，断言更晚修改的文件排在前面，覆盖排序这一核心行为
async def test_glob_matches_and_sorts_by_mtime(tmp_path: Path) -> None:
    old = tmp_path / "old.py"
    old.write_text("x")
    new = tmp_path / "new.py"
    new.write_text("y")
    import os
    import time

    os.utime(old, (time.time() - 100, time.time() - 100))
    result = await GlobTool().invoke({"pattern": "*.py", "path": str(tmp_path)})
    lines = result.content.splitlines()
    assert lines[0].endswith("new.py")
    assert lines[1].endswith("old.py")


# 功能：验证 .git 等目录下的文件不会出现在结果里
# 设计：在 .git 子目录放一个同样匹配 pattern 的文件，断言结果里不包含它，覆盖 SKIP_DIRS 过滤
async def test_glob_skips_git_dir(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hooks.py").write_text("x")
    (tmp_path / "real.py").write_text("y")
    result = await GlobTool().invoke({"pattern": "**/*.py", "path": str(tmp_path)})
    assert "real.py" in result.content
    assert "hooks.py" not in result.content


# 功能：验证无匹配时返回明确的"无结果"提示而不是空字符串
# 设计：空目录搜索，断言 content 非空且包含"no match"类字样，避免下游 LLM 把空字符串误判为工具异常
async def test_glob_no_match_returns_message(tmp_path: Path) -> None:
    result = await GlobTool().invoke({"pattern": "*.nonexistent", "path": str(tmp_path)})
    assert not result.is_error
    assert "no match" in result.content.lower()
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_glob_tool.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'kivi_agent.core.tools.builtin.glob_tool'`）

- [ ] **Step 4: 实现 GlobTool**

```python
# src/kivi_agent/core/tools/builtin/glob_tool.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.tools.builtin._fs_filters import is_skipped

_MAX_RESULTS = 200


class GlobParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = "."


class GlobTool(BaseTool):
    params_model = GlobParams
    name = "glob"
    description = (
        "Find files by name pattern (e.g. '**/*.py', 'src/*.ts'). "
        "Results are sorted by modification time, most recent first. "
        "Skips .git, .venv, node_modules and other common noise directories."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py'.",
            },
            "path": {
                "type": "string",
                "description": "Base directory to search from (default '.').",
            },
        },
        "required": ["pattern"],
    }

    # 按 glob 模式搜索文件名，跳过噪音目录，按 mtime 倒序返回相对路径列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GlobParams.model_validate(params)
        base = Path(p.path)

        if ".." in base.parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        matches = [
            f for f in base.glob(p.pattern)
            if f.is_file() and not is_skipped(f.parts)
        ]
        matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        if not matches:
            return ToolResult(content=f"no matches for pattern: {p.pattern}")

        truncated = len(matches) > _MAX_RESULTS
        shown = matches[:_MAX_RESULTS]
        lines = [str(f) for f in shown]
        if truncated:
            lines.append(f"[truncated: showing {_MAX_RESULTS} of {len(matches)} matches]")

        return ToolResult(content="\n".join(lines))
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_glob_tool.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 注册工具与权限策略**

在 `core/permissions/policy.py::DEFAULT_POLICIES` 加一行：

```python
    "glob":       ToolPolicy(default=PermissionDecision.ALLOW),
```

在 `core/runner.py::_build_registry()` 现有 `registry.register(t)` 循环附近加：

```python
from kivi_agent.core.tools.builtin.glob_tool import GlobTool
# ...
registry.register(GlobTool())
```

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/_fs_filters.py \
        src/kivi_agent/core/tools/builtin/glob_tool.py \
        tests/unit/test_glob_tool.py \
        src/kivi_agent/core/runner.py \
        src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 GlobTool 文件名模式搜索"
```

---

### Task 3: GrepTool — 内容检索

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/grep_tool.py`
- Test: `tests/unit/test_grep_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Consumes: `SKIP_DIRS`/`is_skipped` from Task 2 的 `_fs_filters.py`
- Produces: `class GrepTool(BaseTool)`，`name = "grep"`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_grep_tool.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.tools.builtin.grep_tool import GrepTool


# 功能：验证能在文件内容中按正则找到匹配行，输出 file:line:content 格式
# 设计：写入含目标字符串的文件，断言输出同时包含文件名、行号和命中行内容三个要素
async def test_grep_finds_match(tmp_path: Path) -> None:
    f = tmp_path / "app.py"
    f.write_text("line1\ndef target_func():\n    pass\n")
    result = await GrepTool().invoke({"pattern": "target_func", "path": str(tmp_path)})
    assert not result.is_error
    assert "app.py:2:" in result.content
    assert "target_func" in result.content


# 功能：验证 include 参数能按文件名模式限定搜索范围
# 设计：两个文件一个匹配 include 一个不匹配，断言只有匹配 include 的文件出现在结果里
async def test_grep_respects_include_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("needle\n")
    (tmp_path / "b.txt").write_text("needle\n")
    result = await GrepTool().invoke(
        {"pattern": "needle", "path": str(tmp_path), "include": "*.py"}
    )
    assert "a.py" in result.content
    assert "b.txt" not in result.content


# 功能：验证无匹配时返回明确提示而不是报错
# 设计：搜索一个不存在的字符串，断言 is_error 为 False 且提示信息可读
async def test_grep_no_match_returns_message(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello\n")
    result = await GrepTool().invoke({"pattern": "nonexistent_xyz", "path": str(tmp_path)})
    assert not result.is_error
    assert "no matches" in result.content.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_grep_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 GrepTool**

```python
# src/kivi_agent/core/tools/builtin/grep_tool.py
from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.tools.builtin._fs_filters import is_skipped

_MAX_MATCHES = 200


class GrepParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = "."
    include: str = "**/*"


class GrepTool(BaseTool):
    params_model = GrepParams
    name = "grep"
    description = (
        "Search file contents with a regular expression. "
        "Optionally restrict to files matching an include glob (e.g. '*.py'). "
        "Returns matches as 'file:line:content', truncated at 200 matches."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression to search for."},
            "path": {"type": "string", "description": "Base directory to search from (default '.')."},
            "include": {"type": "string", "description": "Glob to filter which files are searched (default '**/*')."},
        },
        "required": ["pattern"],
    }

    # 在指定目录下按正则搜索文件内容，返回 file:line:content 格式的命中列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GrepParams.model_validate(params)
        base = Path(p.path)

        if ".." in base.parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        try:
            regex = re.compile(p.pattern)
        except re.error as exc:
            return ToolResult(content=f"invalid regex: {exc}", is_error=True, error_type="schema_error")

        matches: list[str] = []
        for f in base.glob(p.include):
            if not f.is_file() or is_skipped(f.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{f}:{lineno}:{line.strip()}")
                    if len(matches) >= _MAX_MATCHES:
                        break
            if len(matches) >= _MAX_MATCHES:
                break

        if not matches:
            return ToolResult(content=f"no matches for pattern: {p.pattern}")

        content = "\n".join(matches)
        if len(matches) >= _MAX_MATCHES:
            content += f"\n[truncated: showing first {_MAX_MATCHES} matches]"

        return ToolResult(content=content)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_grep_tool.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 注册工具与权限策略**

`policy.py`：`"grep": ToolPolicy(default=PermissionDecision.ALLOW),`
`runner.py`：`registry.register(GrepTool())`

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/grep_tool.py tests/unit/test_grep_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 GrepTool 内容检索"
```

---

### Task 4: EditFileTool — 精确文件编辑

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/edit_file.py`
- Test: `tests/unit/test_edit_file_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Produces: `class EditFileTool(BaseTool)`，`name = "edit_file"`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_edit_file_tool.py
from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.tools.builtin.edit_file import EditFileTool


# 功能：验证唯一匹配时能正确替换并原子写回文件
# 设计：写入含唯一目标字符串的文件，替换后重新读取文件内容，确认落盘结果而非只看返回值
async def test_edit_unique_match_replaces(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n")
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "return 1", "new_string": "return 2"}
    )
    assert not result.is_error
    assert f.read_text() == "def foo():\n    return 2\n"


# 功能：验证 old_string 在文件中不存在时返回错误而不是静默无操作
# 设计：传入文件中不存在的字符串，断言 is_error 为 True 且文件内容未被改动
async def test_edit_no_match_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    original = "def foo():\n    return 1\n"
    f.write_text(original)
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "return 999", "new_string": "return 2"}
    )
    assert result.is_error
    assert f.read_text() == original


# 功能：验证 old_string 匹配多处时拒绝执行，避免改错地方
# 设计：文件里放两处相同字符串，断言返回错误且提示"not unique"，文件内容不变
async def test_edit_ambiguous_match_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    original = "x = 1\nx = 1\n"
    f.write_text(original)
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert result.is_error
    assert "unique" in result.content.lower()
    assert f.read_text() == original


# 功能：验证路径穿越（含 ..）被拒绝
# 设计：与 read_file/write_file 保持一致的安全边界，传入 "../secret.py" 断言抛出 PermissionError
async def test_edit_path_traversal_raises() -> None:
    with pytest.raises(PermissionError):
        await EditFileTool().invoke(
            {"path": "../secret.py", "old_string": "a", "new_string": "b"}
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_edit_file_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 EditFileTool**

```python
# src/kivi_agent/core/tools/builtin/edit_file.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult


class EditFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    old_string: str
    new_string: str


class EditFileTool(BaseTool):
    params_model = EditFileParams
    name = "edit_file"
    description = (
        "Replace an exact, unique occurrence of old_string with new_string in a file. "
        "Fails if old_string is not found, or if it appears more than once — "
        "include enough surrounding context in old_string to make the match unique."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file."},
            "old_string": {"type": "string", "description": "Exact text to replace; must be unique in the file."},
            "new_string": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_string", "new_string"],
    }

    # 在文件中唯一匹配 old_string 并替换为 new_string，原子写回；未命中或多处命中时拒绝执行
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EditFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        path = Path(p.path)
        content = path.read_text(encoding="utf-8")  # raises FileNotFoundError if absent

        count = content.count(p.old_string)
        if count == 0:
            return ToolResult(
                content=f"old_string not found in {p.path}",
                is_error=True,
                error_type="runtime_error",
            )
        if count > 1:
            return ToolResult(
                content=f"old_string is not unique in {p.path}: {count} occurrences found",
                is_error=True,
                error_type="runtime_error",
            )

        new_content = content.replace(p.old_string, p.new_string, 1)
        self._atomic_write(path, new_content)

        return ToolResult(content=f"edited {p.path}")

    # 原子写入：先写同目录临时文件，再 rename 覆盖目标，避免写到一半崩溃导致文件损坏
    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_edit_file_tool.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 注册工具与权限策略（高风险，默认 ASK）**

`policy.py`：

```python
    "edit_file":  ToolPolicy(default=PermissionDecision.ASK),
```

同时在 `_PREVIEW_KEY` 加一行 `"edit_file": "path",` 让审批卡片展示被编辑的文件路径。

`runner.py`：`registry.register(EditFileTool())`

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/edit_file.py tests/unit/test_edit_file_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 EditFileTool 精确文件编辑，原子写入"
```

---

### Task 5: DiffTool — 展示两个文件的差异

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/diff_tool.py`
- Test: `tests/unit/test_diff_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Produces: `class DiffTool(BaseTool)`，`name = "diff"`
- 说明：不照搬 mewcode 手写的最长公共前后缀算法，直接用标准库 `difflib.unified_diff`——功能等价、格式更通用，YAGNI 且完全避开"是否复制了 mewcode 算法"的问题。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_diff_tool.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.tools.builtin.diff_tool import DiffTool


# 功能：验证两个内容不同的文件能生成包含 +/- 标记的统一差异格式
# 设计：一个文件改了一行，断言输出里同时有以 "-" 开头的旧行和以 "+" 开头的新行
async def test_diff_shows_changes(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("line1\nline2\nline3\n")
    b.write_text("line1\nCHANGED\nline3\n")
    result = await DiffTool().invoke({"path_a": str(a), "path_b": str(b)})
    assert not result.is_error
    assert "-line2" in result.content
    assert "+CHANGED" in result.content


# 功能：验证两个内容完全相同的文件返回"无差异"提示
# 设计：两个文件内容一致，断言输出明确说明没有差异，而不是返回空字符串造成误解
async def test_diff_identical_files_reports_no_diff(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same\n")
    b.write_text("same\n")
    result = await DiffTool().invoke({"path_a": str(a), "path_b": str(b)})
    assert not result.is_error
    assert "no difference" in result.content.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_diff_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 DiffTool**

```python
# src/kivi_agent/core/tools/builtin/diff_tool.py
from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult

_MAX_DIFF_LINES = 200


class DiffParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path_a: str
    path_b: str


class DiffTool(BaseTool):
    params_model = DiffParams
    name = "diff"
    description = (
        "Show a unified diff between two files (e.g. a file before and after an edit, "
        "or a file in the main worktree vs a task worktree). Output truncated at 200 lines."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path_a": {"type": "string", "description": "Path to the 'before' file."},
            "path_b": {"type": "string", "description": "Path to the 'after' file."},
        },
        "required": ["path_a", "path_b"],
    }

    # 生成两个文件的统一差异（unified diff），无差异时返回明确提示
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = DiffParams.model_validate(params)
        a_lines = Path(p.path_a).read_text(encoding="utf-8").splitlines(keepends=True)
        b_lines = Path(p.path_b).read_text(encoding="utf-8").splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(a_lines, b_lines, fromfile=p.path_a, tofile=p.path_b)
        )

        if not diff_lines:
            return ToolResult(content=f"no difference between {p.path_a} and {p.path_b}")

        truncated = len(diff_lines) > _MAX_DIFF_LINES
        shown = diff_lines[:_MAX_DIFF_LINES]
        content = "".join(shown)
        if truncated:
            content += f"\n[truncated: showing first {_MAX_DIFF_LINES} lines]"

        return ToolResult(content=content)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_diff_tool.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 注册工具与权限策略**

`policy.py`：`"diff": ToolPolicy(default=PermissionDecision.ALLOW),`
`runner.py`：`registry.register(DiffTool())`

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/diff_tool.py tests/unit/test_diff_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 DiffTool 展示文件差异"
```

---

### Task 6: OpenAI 兼容 Provider — 多模型支持

**Files:**
- Modify: `pyproject.toml`（新增 `openai` 依赖）
- Create: `src/kivi_agent/core/llm/openai_compat_provider.py`
- Test: `tests/unit/test_openai_compat_provider.py`

**Interfaces:**
- Consumes: `LLMProvider` Protocol（`core/llm/base.py`）、`LlmResponse`/`ToolCallBlock`/`UsageStats`（`core/llm/types.py`）、`LlmModelSelectedEvent`/`LlmTokenEvent`/`LlmUsageEvent`（`core/bus/events.py`）
- Produces: `class OpenAICompatProvider`，构造签名 `__init__(self, model: str, *, base_url: str, api_key: str, client: Any = None)`，实现与 `AnthropicProvider` 相同的 `async def chat(...) -> LlmResponse`

- [ ] **Step 1: 加依赖**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
uv add openai
```

- [ ] **Step 2: 写失败测试（用假 client 注入，不打真实网络请求）**

```python
# tests/unit/test_openai_compat_provider.py
from __future__ import annotations

from types import SimpleNamespace

from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider


class _FakeStreamChunk:
    def __init__(self, delta_content: str | None = None, tool_call: dict[str, object] | None = None,
                 finish_reason: str | None = None) -> None:
        delta = SimpleNamespace(content=delta_content, tool_calls=None)
        if tool_call is not None:
            delta.tool_calls = [SimpleNamespace(
                index=0,
                id=tool_call["id"],
                function=SimpleNamespace(name=tool_call["name"], arguments=tool_call["arguments"]),
            )]
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5) if finish_reason else None


class _FakeStream:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> "_FakeStream":
        return self

    async def __anext__(self) -> _FakeStreamChunk:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeCompletions:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    async def create(self, **kwargs: object) -> _FakeStream:
        return _FakeStream(list(self._chunks))


class _FakeChat:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self.completions = _FakeCompletions(chunks)


class _FakeOpenAIClient:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self.chat = _FakeChat(chunks)


# 功能：验证纯文本回复（无工具调用）能正确聚合成 LlmResponse.text 且 stop_reason 为 end_turn
# 设计：模拟 OpenAI 流式返回两个文本增量 chunk + 一个 finish_reason="stop" chunk，断言拼接结果和用量统计
async def test_chat_aggregates_text_response() -> None:
    chunks = [
        _FakeStreamChunk(delta_content="hel"),
        _FakeStreamChunk(delta_content="lo"),
        _FakeStreamChunk(finish_reason="stop"),
    ]
    provider = OpenAICompatProvider(
        model="test-model", base_url="http://fake", api_key="x",
        client=_FakeOpenAIClient(chunks),
    )
    bus = EventBus()
    response = await provider.chat([], [], bus, run_id="r1")
    assert response.text == "hello"
    assert response.stop_reason == "end_turn"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 5


# 功能：验证工具调用流式返回能正确解析成 ToolCallBlock 且 stop_reason 为 tool_use
# 设计：模拟一个 finish_reason="tool_calls" 的 chunk 携带函数名和参数，断言 tool_calls 列表内容
async def test_chat_parses_tool_call() -> None:
    chunks = [
        _FakeStreamChunk(tool_call={"id": "call_1", "name": "bash", "arguments": '{"command": "ls"}'}),
        _FakeStreamChunk(finish_reason="tool_calls"),
    ]
    provider = OpenAICompatProvider(
        model="test-model", base_url="http://fake", api_key="x",
        client=_FakeOpenAIClient(chunks),
    )
    bus = EventBus()
    response = await provider.chat([], [], bus, run_id="r1")
    assert response.stop_reason == "tool_use"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "bash"
    assert response.tool_calls[0].input == {"command": "ls"}
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_openai_compat_provider.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 4: 实现 OpenAICompatProvider**

```python
# src/kivi_agent/core/llm/openai_compat_provider.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI

from kivi_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

_DEFAULT_CONTEXT_WINDOW = 128_000


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把 Anthropic 风格的工具 schema（name/description/input_schema）转换成 OpenAI function-calling 格式
def _convert_tool_schema(tool: dict[str, object]) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


class OpenAICompatProvider:
    # 初始化 OpenAI 兼容客户端；client 可在测试时注入以跳过真实网络请求
    def __init__(self, model: str, *, base_url: str, api_key: str, client: Any = None) -> None:
        self._model = model
        self._client: Any = client or AsyncOpenAI(base_url=base_url, api_key=api_key)

    # 流式调用 OpenAI 兼容 Chat Completions API，聚合增量为完整 LlmResponse
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        await bus.publish(
            LlmModelSelectedEvent(run_id=run_id, model=self._model, strategy="static", ts=_now())
        )

        openai_messages: list[dict[str, object]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": openai_messages,
            "stream": True,
        }
        if tool_schemas:
            kwargs["tools"] = [_convert_tool_schema(t) for t in tool_schemas]

        stream = await self._client.chat.completions.create(**kwargs)

        text_parts: list[str] = []
        tool_call_buffers: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        usage: Any = None

        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if delta.content:
                text_parts.append(delta.content)
                await bus.publish(LlmTokenEvent(run_id=run_id, token=delta.content, ts=_now()))
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    buf = tool_call_buffers.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        buf["id"] = tc.id
                    if tc.function.name:
                        buf["name"] = tc.function.name
                    if tc.function.arguments:
                        buf["arguments"] += tc.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason
                usage = chunk.usage

        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        context_pct = input_tokens / _DEFAULT_CONTEXT_WINDOW

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
                ts=_now(),
            )
        )

        tool_calls = [
            ToolCallBlock(id=buf["id"], name=buf["name"], input=json.loads(buf["arguments"] or "{}"))
            for buf in tool_call_buffers.values()
        ]

        return LlmResponse(
            stop_reason="tool_use" if tool_calls else "end_turn",
            tool_calls=tool_calls,
            text="".join(text_parts),
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                context_pct=context_pct,
            ),
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_openai_compat_provider.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml uv.lock src/kivi_agent/core/llm/openai_compat_provider.py \
        tests/unit/test_openai_compat_provider.py
git commit -m "feat: 新增 OpenAI 兼容 Provider，支持流式文本与工具调用"
```

---

### Task 7: 配置与接入点改造 — 按配置选择 Provider

**Files:**
- Modify: `src/kivi_agent/core/config.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/app.py`
- Test: `tests/unit/test_config_env.py`（追加用例）

**Interfaces:**
- Consumes: Task 6 的 `OpenAICompatProvider`
- Produces: `LlmConfig.provider: str`（`"anthropic" | "openai_compat"`）、`LlmConfig.openai_base_url: str | None`、辅助函数 `build_provider(config: KamaConfig) -> LLMProvider`（新建于 `core/llm/factory.py`）

- [ ] **Step 1: 写失败测试（配置解析）**

```python
# tests/unit/test_config_env.py 追加
# 功能：验证 llm.provider 和 llm.openai_base_url 能从 TOML 正确解析
# 设计：构造包含 [llm] 新字段的临时 TOML，断言解析后的 KamaConfig.llm 字段值，覆盖新配置项的读取路径
def test_llm_provider_and_openai_base_url_from_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[llm]\nprovider = "openai_compat"\nopenai_base_url = "https://api.example.com/v1"\n'
    )
    monkeypatch.setenv("KAMA_CONFIG", str(config_file))
    from kivi_agent.core.config import get_config
    config = get_config()
    assert config.llm.provider == "openai_compat"
    assert config.llm.openai_base_url == "https://api.example.com/v1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_config_env.py -k openai_base_url -v`
Expected: FAIL（`Unknown [llm] keys: openai_base_url, provider`）

- [ ] **Step 3: 扩展 LlmConfig 和校验逻辑**

在 `core/config.py` 的 `LlmConfig` dataclass 里加字段：

```python
@dataclass
class LlmConfig:
    default_model: str = _DEFAULT_MODEL
    router: str = "static"  # "static" | "rule_based" (S4) | "cost_budget" (S6)
    provider: str = "anthropic"  # "anthropic" | "openai_compat"
    openai_base_url: str | None = None
```

在 `_apply_toml` 的 `if "llm" in data:` 块内，把 `unknown_llm` 白名单扩成 `{"default_model", "router", "provider", "openai_base_url"}`，并追加：

```python
        if "provider" in llm:
            val = llm["provider"]
            if val not in ("anthropic", "openai_compat"):
                raise SystemExit("Config error: llm.provider must be 'anthropic' or 'openai_compat'")
            config.llm.provider = val
        if "openai_base_url" in llm:
            val = llm["openai_base_url"]
            if not isinstance(val, str):
                raise SystemExit("Config error: llm.openai_base_url must be a string")
            config.llm.openai_base_url = val
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_config_env.py -k openai_base_url -v`
Expected: PASS

- [ ] **Step 5: 新建 Provider 工厂函数**

```python
# src/kivi_agent/core/llm/factory.py
from __future__ import annotations

import os

from kivi_agent.core.config import KamaConfig
from kivi_agent.core.llm.base import LLMProvider
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider
from kivi_agent.core.llm.provider import AnthropicProvider


# 根据配置构造对应的 LLMProvider 实例（Anthropic 或 OpenAI 兼容）
def build_provider(config: KamaConfig) -> LLMProvider:
    if config.llm.provider == "openai_compat":
        base_url = config.llm.openai_base_url
        if not base_url:
            raise SystemExit("llm.openai_base_url must be set when llm.provider = 'openai_compat'")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY not set")
        return OpenAICompatProvider(config.llm.default_model, base_url=base_url, api_key=api_key)
    return AnthropicProvider(config.llm.default_model)
```

- [ ] **Step 6: 接入 runner.py 和 app.py**

`core/runner.py` 第 191 行附近，把：

```python
provider: LLMProvider = self._provider or AnthropicProvider(
    self._config.llm.default_model
)
```

替换为：

```python
provider: LLMProvider = self._provider or build_provider(self._config)
```

并把 import 从 `from kivi_agent.core.llm.provider import AnthropicProvider` 改为 `from kivi_agent.core.llm.factory import build_provider`（若其他地方仍用 `AnthropicProvider` 保留原 import）。

`core/app.py` 第 236 行附近，把：

```python
compact_provider = AnthropicProvider(self._config.llm.default_model)
```

替换为：

```python
compact_provider = build_provider(self._config)
```

并加 `from kivi_agent.core.llm.factory import build_provider`。

- [ ] **Step 7: 回归测试**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过（含之前已存在的 `test_runner.py`、`test_llm_provider.py`）

- [ ] **Step 8: 提交**

```bash
git add src/kivi_agent/core/config.py src/kivi_agent/core/llm/factory.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/app.py tests/unit/test_config_env.py
git commit -m "feat: 支持通过配置在 Anthropic / OpenAI 兼容 Provider 间切换"
```

---

### Task 8: 工作树管理模块 — Git Worktree 生命周期

**Files:**
- Create: `src/kivi_agent/core/workspace/__init__.py`
- Create: `src/kivi_agent/core/workspace/worktree.py`
- Test: `tests/unit/test_worktree.py`

**Interfaces:**
- Produces: `@dataclass class WorktreeInfo: path: Path; branch: str; base_branch: str`
- Produces: `def slugify(name: str) -> str`
- Produces: `async def create_worktree(repo_root: Path, name: str, base_branch: str = "HEAD") -> WorktreeInfo`
- Produces: `async def remove_worktree(repo_root: Path, info: WorktreeInfo, *, force: bool = False) -> None`

- [ ] **Step 1: 写失败测试（用真实临时 Git 仓库，不 mock，因为逻辑核心就是 git 命令编排）**

```python
# tests/unit/test_worktree.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kivi_agent.core.workspace.worktree import create_worktree, remove_worktree, slugify


# 每个测试用例在 tmp_path 下建一个最小可用的 git 仓库并提交一次
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


# 功能：验证任意任务名能生成合法的 git 分支/目录 slug（小写、无空格、无特殊字符）
# 设计：传入含空格和大写字母的任务名，断言输出只含小写字母数字和连字符
def test_slugify_normalizes_name() -> None:
    assert slugify("Fix Login Bug!!") == "fix-login-bug"


# 功能：验证 create_worktree 能在仓库下创建独立目录和分支，且新目录包含仓库文件
# 设计：调用后检查返回的 WorktreeInfo.path 存在且含 README.md，同时用 git worktree list 交叉验证分支确实被 git 记录
async def test_create_worktree_creates_isolated_dir(repo: Path) -> None:
    info = await create_worktree(repo, "task one")
    assert info.path.exists()
    assert (info.path / "README.md").exists()
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert str(info.path) in listing


# 功能：验证 remove_worktree 能干净回收工作树目录和对应分支
# 设计：先创建再移除，断言目录不再存在，且 git worktree list 里也不再出现该分支
async def test_remove_worktree_cleans_up(repo: Path) -> None:
    info = await create_worktree(repo, "task two")
    await remove_worktree(repo, info, force=True)
    assert not info.path.exists()
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert str(info.path) not in listing
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_worktree.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 worktree.py**

```python
# src/kivi_agent/core/workspace/worktree.py
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class WorktreeInfo:
    path: Path
    branch: str
    base_branch: str


# 把任意字符串规范化为小写、连字符分隔、仅含字母数字的 slug，用作分支名和目录名
def slugify(name: str) -> str:
    lowered = name.lower()
    slug = _SLUG_RE.sub("-", lowered).strip("-")
    return slug or "task"


# 运行一个子进程命令，失败时抛出带 stderr 内容的 RuntimeError
async def _run_git(args: list[str], cwd: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.decode('utf-8', errors='replace')}")


# 为任务创建一个独立的 Git 工作树，分支名和目录名都基于 name 生成的 slug
async def create_worktree(repo_root: Path, name: str, base_branch: str = "HEAD") -> WorktreeInfo:
    slug = slugify(name)
    branch = f"kivi-agent-{slug}"
    worktree_path = repo_root / ".kivi" / "worktrees" / slug
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    await _run_git(
        ["worktree", "add", "-B", branch, str(worktree_path), base_branch],
        cwd=repo_root,
    )
    return WorktreeInfo(path=worktree_path, branch=branch, base_branch=base_branch)


# 回收工作树：先移除工作树目录，再删除对应分支；force=True 时忽略未提交改动强制移除
async def remove_worktree(repo_root: Path, info: WorktreeInfo, *, force: bool = False) -> None:
    args = ["worktree", "remove", str(info.path)]
    if force:
        args.append("--force")
    await _run_git(args, cwd=repo_root)
    await _run_git(["branch", "-D", info.branch], cwd=repo_root)
```

```python
# src/kivi_agent/core/workspace/__init__.py
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_worktree.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/workspace/ tests/unit/test_worktree.py
git commit -m "feat: 新增 Git 工作树生命周期管理模块"
```

---

### Task 9: EnterWorktreeTool / ExitWorktreeTool

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/enter_worktree.py`
- Create: `src/kivi_agent/core/tools/builtin/exit_worktree.py`
- Test: `tests/unit/test_worktree_tools.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Consumes: Task 8 的 `create_worktree`/`remove_worktree`/`WorktreeInfo`
- Produces: `class EnterWorktreeTool(BaseTool)`（`name = "enter_worktree"`）、`class ExitWorktreeTool(BaseTool)`（`name = "exit_worktree"`）
- 设计简化：与 mewcode 的"切换进程 cwd"模型不同，这里工具是无状态的——`enter_worktree` 直接返回新工作树的绝对路径，后续 `bash`/`edit_file` 等工具调用由 Agent 显式带上这个路径前缀操作，不做全局 cwd 切换（避免并发任务之间互相污染 cwd）。这一点在两个工具的 `description` 里向 LLM 说明。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_worktree_tools.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kivi_agent.core.tools.builtin.enter_worktree import EnterWorktreeTool
from kivi_agent.core.tools.builtin.exit_worktree import ExitWorktreeTool


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


# 功能：验证 EnterWorktreeTool 返回的路径确实是新建的独立工作树目录
# 设计：调用工具后断言返回内容里的路径存在且含仓库文件，说明工作树创建成功
async def test_enter_worktree_returns_isolated_path(repo: Path) -> None:
    result = await EnterWorktreeTool().invoke({"repo_root": str(repo), "name": "demo task"})
    assert not result.is_error
    path_str = result.content.strip().splitlines()[-1]
    assert Path(path_str).exists()
    assert (Path(path_str) / "README.md").exists()


# 功能：验证 ExitWorktreeTool 能按路径把工作树清理掉
# 设计：先 enter 再 exit，断言 exit 后目录不存在，形成完整生命周期闭环
async def test_exit_worktree_removes_directory(repo: Path) -> None:
    enter_result = await EnterWorktreeTool().invoke({"repo_root": str(repo), "name": "demo task 2"})
    path_str = enter_result.content.strip().splitlines()[-1]
    exit_result = await ExitWorktreeTool().invoke(
        {"repo_root": str(repo), "path": path_str, "branch": f"kivi-agent-{'demo-task-2'}"}
    )
    assert not exit_result.is_error
    assert not Path(path_str).exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_worktree_tools.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现两个工具**

```python
# src/kivi_agent/core/tools/builtin/enter_worktree.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.workspace.worktree import create_worktree


class EnterWorktreeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repo_root: str
    name: str
    base_branch: str = "HEAD"


class EnterWorktreeTool(BaseTool):
    params_model = EnterWorktreeParams
    name = "enter_worktree"
    description = (
        "Create an isolated Git worktree for a task, on its own branch, so file edits and "
        "commands don't touch the main working directory. Returns the absolute path of the "
        "new worktree — use that path as the base for subsequent file and bash operations "
        "for this task (this tool does not change the process's current directory)."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string", "description": "Path to the main Git repository."},
            "name": {"type": "string", "description": "Short task name, used to derive branch/dir name."},
            "base_branch": {"type": "string", "description": "Branch to base the worktree on (default HEAD)."},
        },
        "required": ["repo_root", "name"],
    }

    # 为任务创建独立 Git 工作树，返回其绝对路径供后续工具调用使用
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EnterWorktreeParams.model_validate(params)
        info = await create_worktree(Path(p.repo_root), p.name, p.base_branch)
        return ToolResult(
            content=f"created isolated worktree on branch {info.branch}\n{info.path}"
        )
```

```python
# src/kivi_agent/core/tools/builtin/exit_worktree.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.workspace.worktree import WorktreeInfo, remove_worktree


class ExitWorktreeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repo_root: str
    path: str
    branch: str


class ExitWorktreeTool(BaseTool):
    params_model = ExitWorktreeParams
    name = "exit_worktree"
    description = (
        "Discard a task's isolated worktree created by enter_worktree: removes the worktree "
        "directory and deletes its branch. Any uncommitted changes in that worktree are lost — "
        "make sure the work has been committed or is no longer needed before calling this."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string", "description": "Path to the main Git repository."},
            "path": {"type": "string", "description": "Worktree path returned by enter_worktree."},
            "branch": {"type": "string", "description": "Worktree branch name returned by enter_worktree."},
        },
        "required": ["repo_root", "path", "branch"],
    }

    # 移除指定的 Git 工作树目录及其分支
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ExitWorktreeParams.model_validate(params)
        info = WorktreeInfo(path=Path(p.path), branch=p.branch, base_branch="")
        await remove_worktree(Path(p.repo_root), info, force=True)
        return ToolResult(content=f"removed worktree {p.path} and branch {p.branch}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_worktree_tools.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 注册工具与权限策略**

`policy.py`：

```python
    "enter_worktree": ToolPolicy(default=PermissionDecision.ALLOW),
    "exit_worktree":  ToolPolicy(default=PermissionDecision.ASK),
```

`_PREVIEW_KEY` 加：`"enter_worktree": "name", "exit_worktree": "path",`

`runner.py`：

```python
registry.register(EnterWorktreeTool())
registry.register(ExitWorktreeTool())
```

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/enter_worktree.py \
        src/kivi_agent/core/tools/builtin/exit_worktree.py \
        tests/unit/test_worktree_tools.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 enter_worktree / exit_worktree 工具，工具态生命周期挂到 Git 工作树"
```

---

### Task 10: 命令沙箱 — macOS Seatbelt / Linux Bubblewrap

**Files:**
- Create: `src/kivi_agent/core/sandbox/__init__.py`
- Create: `src/kivi_agent/core/sandbox/seatbelt.py`
- Create: `src/kivi_agent/core/sandbox/bwrap.py`
- Test: `tests/unit/test_sandbox.py`

**Interfaces:**
- Produces: `class Sandbox(Protocol): def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str: ...`
- Produces: `def create_sandbox() -> Sandbox | None`（按 `platform.system()` 选择实现，非 macOS/Linux 返回 `None`）
- Produces: `class SeatbeltSandbox`、`class BwrapSandbox`

- [ ] **Step 1: 写失败测试（只测命令拼装逻辑，不依赖真的装了 sandbox-exec/bwrap）**

```python
# tests/unit/test_sandbox.py
from __future__ import annotations

from kivi_agent.core.sandbox.bwrap import BwrapSandbox
from kivi_agent.core.sandbox.seatbelt import SeatbeltSandbox


# 功能：验证 SeatbeltSandbox.wrap 生成的命令以 sandbox-exec 开头并内嵌原始命令
# 设计：只校验拼装出的字符串结构（不实际执行），因为单元测试环境不一定是 macOS
def test_seatbelt_wrap_builds_sandbox_exec_command() -> None:
    sb = SeatbeltSandbox()
    wrapped = sb.wrap("echo hi", allow_write=["/tmp/work"], network=False)
    assert wrapped.startswith("/usr/bin/sandbox-exec")
    assert "echo hi" in wrapped
    assert "/tmp/work" in wrapped


# 功能：验证 network=True 时 Seatbelt profile 里包含允许网络的规则，network=False 时不包含
# 设计：分别用两种取值调用，断言 profile 文本里 "allow network*" 的出现与否，覆盖网络隔离开关
def test_seatbelt_network_toggle() -> None:
    sb = SeatbeltSandbox()
    with_net = sb.wrap("curl x", allow_write=[], network=True)
    without_net = sb.wrap("curl x", allow_write=[], network=False)
    assert "allow network*" in with_net
    assert "allow network*" not in without_net


# 功能：验证 BwrapSandbox.wrap 生成的命令以 bwrap 开头，且对 allow_write 路径加了可写 bind
# 设计：校验命令行参数片段而非真实执行，覆盖只读根 + 可写目录 bind 的核心逻辑
def test_bwrap_wrap_builds_bind_mounts() -> None:
    sb = BwrapSandbox()
    wrapped = sb.wrap("echo hi", allow_write=["/tmp/work"], network=False)
    assert wrapped.startswith("bwrap")
    assert "--bind /tmp/work /tmp/work" in wrapped
    assert "--unshare-net" in wrapped
    assert "echo hi" in wrapped
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_sandbox.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 seatbelt.py**

```python
# src/kivi_agent/core/sandbox/seatbelt.py
from __future__ import annotations

import shlex


class SeatbeltSandbox:
    # 用 macOS sandbox-exec 包装命令：默认拒绝一切，显式放行只读、指定目录可写和可选网络
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str:
        write_rules = "\n".join(
            f'(allow file-write* (subpath "{path}"))' for path in allow_write
        )
        network_rule = "(allow network*)" if network else ""
        profile = f"""(version 1)
(deny default)
(allow file-read*)
{write_rules}
{network_rule}
(allow process-fork)
(allow process-exec)
"""
        return f"/usr/bin/sandbox-exec -p {shlex.quote(profile)} bash -c {shlex.quote(command)}"
```

- [ ] **Step 4: 实现 bwrap.py**

```python
# src/kivi_agent/core/sandbox/bwrap.py
from __future__ import annotations

import shlex


class BwrapSandbox:
    # 用 Linux bubblewrap 包装命令：根文件系统只读挂载，allow_write 里的目录改为可写 bind，可选禁网
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str:
        args = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
        for path in allow_write:
            args.extend(["--bind", path, path])
        if not network:
            args.append("--unshare-net")
        args.extend(["bash", "-c", command])
        return " ".join(shlex.quote(a) if " " in a else a for a in args)
```

- [ ] **Step 5: 实现工厂 `__init__.py`**

```python
# src/kivi_agent/core/sandbox/__init__.py
from __future__ import annotations

import platform
from typing import Protocol


class Sandbox(Protocol):
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str: ...


# 按当前操作系统选择沙箱实现；不支持的平台返回 None（调用方应回退为不沙箱执行并给出警告）
def create_sandbox() -> Sandbox | None:
    system = platform.system()
    if system == "Darwin":
        from kivi_agent.core.sandbox.seatbelt import SeatbeltSandbox
        return SeatbeltSandbox()
    if system == "Linux":
        from kivi_agent.core.sandbox.bwrap import BwrapSandbox
        return BwrapSandbox()
    return None
```

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_sandbox.py -v`
Expected: PASS（3 passed）

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/sandbox/ tests/unit/test_sandbox.py
git commit -m "feat: 新增 macOS Seatbelt / Linux Bubblewrap 命令沙箱"
```

---

### Task 11: 把沙箱接入 BashTool，并完成端到端手动验收

**Files:**
- Modify: `src/kivi_agent/core/tools/builtin/bash.py`
- Modify: `src/kivi_agent/core/runner.py`
- Test: `tests/unit/test_builtin_tools.py`（追加用例）
- Create: `docs/迁移记录/最小闭环验收记录.md`

**Interfaces:**
- Consumes: Task 10 的 `Sandbox` Protocol / `create_sandbox()`
- Produces: `BashTool.__init__(self, sandbox: Sandbox | None = None, allow_write: list[str] | None = None)`

- [ ] **Step 1: 写失败测试（验证注入 sandbox 后命令被包装）**

```python
# tests/unit/test_builtin_tools.py 追加
# 功能：验证注入 sandbox 后，BashTool 实际执行的是被 wrap 过的命令而不是原始命令
# 设计：注入一个记录收到的命令字符串的假 sandbox，断言它的 wrap() 被调用且其返回值确实被 create_subprocess_shell 使用
async def test_bash_tool_uses_sandbox_when_provided(monkeypatch):
    from kivi_agent.core.tools.builtin.bash import BashTool

    class _FakeSandbox:
        def __init__(self):
            self.wrapped_commands: list[str] = []

        def wrap(self, command, *, allow_write, network=False):
            self.wrapped_commands.append(command)
            return f"echo wrapped:{command}"

    fake = _FakeSandbox()
    tool = BashTool(sandbox=fake, allow_write=["/tmp"])
    result = await tool.invoke({"command": "echo real"})
    assert not result.is_error
    assert fake.wrapped_commands == ["echo real"]
    assert "wrapped:echo real" in result.content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_builtin_tools.py -k uses_sandbox -v`
Expected: FAIL（`TypeError: BashTool() takes no arguments` 或类似）

- [ ] **Step 3: 改造 BashTool，支持可选沙箱注入**

在 `core/tools/builtin/bash.py` 里，`class BashTool(BaseTool):` 之后加构造函数，并在 `invoke` 里用它包装命令：

```python
class BashTool(BaseTool):
    params_model = BashParams
    name = "bash"
    description = (
        "Execute a shell command and return its output (stdout + stderr combined). "
        "Non-interactive only — commands requiring user input will hang and time out. "
        "Prefer short, focused commands. Output is truncated at 64 KB. "
        "May run inside a filesystem/network sandbox depending on configuration."
    )
    input_schema: dict[str, object] = { ... }  # 保持不变

    # 可选注入沙箱与允许写入的目录；sandbox 为 None 时按原有方式直接执行
    def __init__(self, sandbox: "Sandbox | None" = None, allow_write: list[str] | None = None) -> None:
        self._sandbox = sandbox
        self._allow_write = allow_write or [str(Path.cwd())]

    # 在子进程中执行 shell 命令（如配置了沙箱则先包装），合并 stdout/stderr，超时或非零退出码时返回错误
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = BashParams.model_validate(params)
        command = p.command
        timeout = p.timeout

        if self._sandbox is not None:
            command = self._sandbox.wrap(command, allow_write=self._allow_write, network=False)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            # ... 其余逻辑不变
```

同时在文件顶部加：

```python
from pathlib import Path

from kivi_agent.core.sandbox import Sandbox
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_builtin_tools.py -k uses_sandbox -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过

Run: `uv run ruff check src tests`
Expected: 无报错

Run: `uv run mypy src`
Expected: 无报错（若 openai/mewcode 相关第三方库缺类型 stub，按仓库既有 mypy 配置忽略即可，不新增全局忽略规则）

- [ ] **Step 6: 在 `_build_registry()` 里用沙箱构造 BashTool**

把 `runner.py` 里原来 `registry.register(t)` 循环中构造 `BashTool()` 的地方改为：

```python
from kivi_agent.core.sandbox import create_sandbox
# ...
registry.register(BashTool(sandbox=create_sandbox(), allow_write=[str(child_runs_dir)]))
```

（若原先是无参 `BashTool()` 混在一个工具实例列表里，单独把这一行拆出来，不影响其余工具的注册方式。）

- [ ] **Step 7: 手动端到端验收，并记录结果**

在本机（非测试环境）实际跑一遍最小闭环：

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
uv run kivi-core &            # 启动 daemon
uv run kivi-tui                # 打开 TUI，发起一个真实代码修改目标，例如：
                                # "在当前仓库里找到 DiffTool 类，给它的 description 末尾加一句话"
```

验收动作对照《kamaAgent 企业 Agent 平台整合方案》第 21 章的 7 步闭环逐条打勾：

1. 通过 TUI 发起真实代码修改任务
2. Core 通过 `build_provider()` 选择的 Provider（Anthropic 或配置好的 OpenAI 兼容端点）完成规划
3. Agent 依次调用 `grep`/`glob` 定位代码、`edit_file` 精确修改、`diff` 展示改动
4. 修改实际发生在 `enter_worktree` 创建的独立 Git 工作树内，主工作区未被触碰（`git status` 确认）
5. `bash` 类高风险操作经沙箱包装执行，并触发 TUI 审批卡片
6. 用户在 TUI 里看到 diff 后选择接受
7. 全过程在 `~/.kivi/sessions/<sid>/events.jsonl` 里留下完整可回放事件

把每一步"通过/不通过 + 实际现象"写入验收记录：

```markdown
# 最小闭环验收记录

日期：2026-xx-xx

| 步骤 | 结果 | 备注 |
|---|---|---|
| 1. TUI 发起任务 | | |
| 2. Provider 规划 | | |
| 3. glob/grep/edit_file/diff 工具链 | | |
| 4. 独立工作树隔离 | | |
| 5. 沙箱执行 + 审批 | | |
| 6. Diff 审查确认 | | |
| 7. 事件可回放 | | |

未通过项与后续修复计划：
```

- [ ] **Step 8: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/bash.py src/kivi_agent/core/runner.py \
        tests/unit/test_builtin_tools.py docs/迁移记录/最小闭环验收记录.md
git commit -m "feat: BashTool 接入沙箱；完成个人最小闭环端到端验收"
```

---

## Self-Review Notes

- **覆盖范围**：11 个任务覆盖了《整合方案》第 21 章"首轮落地建议"列出的全部 7 个验收点（多模型 Provider、真实编程工具链、工作树隔离、沙箱执行、可恢复审批、diff 审查、事件可回放——最后一项复用 kivi-agent 已有的 `EventWriter`，不需要新任务）。
- **有意排除的范围**（明确不在本计划内，属于团队级任务）：新建仓库、Gateway/多客户端、企业身份认证与审计、模型网关、macOS 之外的多 Worker 高可用、技能市场、知识库/运维等业务能力包。这些对应方案里阶段 4 之后的内容，个人执行没有意义。
- **类型一致性**：`GlobTool`/`GrepTool`/`EditFileTool`/`DiffTool`/`EnterWorktreeTool`/`ExitWorktreeTool` 均严格复用 Task 前置研究确认的 `BaseTool`/`ToolResult`/`params_model` 签名；`OpenAICompatProvider.chat()` 签名与 `AnthropicProvider.chat()`、`LLMProvider` Protocol 完全一致；`Sandbox.wrap()` 签名在 Task 10 定义后在 Task 11 原样使用，未出现改名。
