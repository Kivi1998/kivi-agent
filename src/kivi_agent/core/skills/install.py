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
