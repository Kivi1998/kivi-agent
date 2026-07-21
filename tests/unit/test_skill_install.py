from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kama_claude.core.skills.install import SkillInstallError, install_skill


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
