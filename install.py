#!/usr/bin/env python3
"""localagentskills — 跨平台安装脚本 (macOS / Linux / Windows)

一键安装/卸载技能到 Claude Code 或 Codex。

用法:
  python3 install.py                          # 安装全部技能到两个平台
  python3 install.py --target claude          # 只安装到 Claude Code
  python3 install.py --skill web-novel-downloader  # 只安装指定技能
  python3 install.py --pip                    # 安装全部并装 Python 依赖
  python3 install.py --list                   # 列出可用技能
  python3 install.py --uninstall              # 卸载全部
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shutil
import stat
import tempfile
from datetime import date
from pathlib import Path

# ── 跨平台常量 ────────────────────────────────────────────────

REPO_DIR = Path(__file__).resolve().parent
SKILLS_DIR = REPO_DIR / "skills"
MANIFEST = REPO_DIR / "skills-manifest.json"

# Claude Code / Codex 技能目录
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
CODEX_SKILLS = Path.home() / ".codex" / "skills"

# ANSI 颜色（Windows 10+ 终端均支持）
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
DIM = "\033[2m"
BOLD = "\033[1m"
NC = "\033[0m"  # reset


# ── 辅助函数 ──────────────────────────────────────────────────

def _can_symlink() -> bool:
    """检测当前平台是否支持符号链接。"""
    if sys.platform != "win32":
        return True
    # Windows: 需要管理员权限或开发者模式
    try:
        test_src = SKILLS_DIR / ".symlink_test_src"
        test_dst = SKILLS_DIR / ".symlink_test_dst"
        test_src.mkdir(parents=True, exist_ok=True)
        os.symlink(str(test_src), str(test_dst))
        test_dst.unlink()
        test_src.rmdir()
        return True
    except OSError:
        return False


CAN_SYMLINK: bool = _can_symlink()


def link_or_copy(src: Path, dst: Path) -> str:
    """创建符号链接；Windows 无权限时回退到复制。

    返回操作类型: "linked" / "copied" / "junction"
    """
    if CAN_SYMLINK:
        os.symlink(str(src), str(dst), target_is_directory=src.is_dir())
        return "linked"
    elif sys.platform == "win32":
        # 尝试 junction (仅目录、仅 NTFS)
        try:
            import _winapi
            _winapi.CreateJunction(str(src), str(dst))
            return "junction"
        except (OSError, ImportError, AttributeError):
            pass
        # 最后手段：复制
        shutil.copytree(str(src), str(dst))
        return "copied (fallback — symlink not available)"
    else:
        shutil.copytree(str(src), str(dst))
        return "copied (fallback)"


def is_symlink_or_junction(path: Path) -> bool:
    """判断 path 是否为符号链接或 Windows junction。"""
    if path.is_symlink():
        return True
    if sys.platform == "win32":
        try:
            attrs = path.lstat().st_file_attributes
            return bool(attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except (AttributeError, OSError):
            return False
    return False


def read_symlink_target(path: Path) -> str | None:
    """读取符号链接目标（跨平台）。"""
    try:
        return os.readlink(str(path))
    except OSError:
        return None


def project_skill_present(path: Path) -> bool:
    """Return True when a project skill entry exists, including broken symlinks."""
    return path.exists() or path.is_symlink() or is_symlink_or_junction(path)


def remove_link_or_junction(path: Path) -> None:
    """删除符号链接或 Windows junction，不递归删除真实目标。"""
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        path.rmdir()
    else:
        path.unlink()


def pip_install(req_path: Path) -> bool:
    """pip install -r requirements.txt，成功返回 True。"""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_path)],
            check=True, capture_output=True, text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def read_description(skill_dir: Path) -> str:
    """从 SKILL.md frontmatter 中读取 description。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return ""
    try:
        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()
        in_front = False
        for index, line in enumerate(lines):
            if line.strip() == "---":
                if not in_front:
                    in_front = True
                    continue
                else:
                    break
            if in_front and line.startswith("description:"):
                value = line.split(":", 1)[1].strip()
                if value in {">", ">-", "|", "|-"}:
                    parts = []
                    for follow in lines[index + 1:]:
                        if follow.strip() == "---" or (follow and not follow.startswith((" ", "\t"))):
                            break
                        stripped = follow.strip()
                        if stripped:
                            parts.append(stripped)
                    value = " ".join(parts)
                value = value.strip().strip("\"'")
                return " ".join(value.split())[:80]
    except Exception:
        pass
    return ""


# ── 核心逻辑 ──────────────────────────────────────────────────

def list_skills() -> None:
    """列出 skills/ 下所有可用技能。"""
    if not SKILLS_DIR.is_dir():
        print(f"{YELLOW}No skills directory found.{NC}")
        return
    print(f"{CYAN}Available skills:{NC}")
    for d in sorted(SKILLS_DIR.iterdir()):
        if d.is_dir() and (d / "SKILL.md").is_file():
            desc = read_description(d)
            print(f"  {GREEN}{d.name:<30}{NC} {desc}")


def select_skills(names: list[str] | None = None) -> list[Path]:
    """返回选中的技能目录列表。names=None 表示全部。"""
    if not SKILLS_DIR.is_dir():
        return []
    if names:
        selected = []
        for name in names:
            d = SKILLS_DIR / name
            if d.is_dir() and (d / "SKILL.md").is_file():
                selected.append(d)
            else:
                print(f"{RED}Skill not found: {name}{NC}")
                sys.exit(1)
        return selected
    return [d for d in sorted(SKILLS_DIR.iterdir())
            if d.is_dir() and (d / "SKILL.md").is_file()]


def shorten(text: str, limit: int = 58) -> str:
    """压缩描述文本，便于选择列表展示。"""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rfind(" ")
    return text[:cut if cut > 20 else limit].rstrip() + "..."


def parse_selection(selection: str, max_index: int) -> list[int]:
    """解析 1 3 5 或 1-4 这样的编号选择。"""
    indexes: list[int] = []
    for part in selection.replace(",", " ").split():
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                continue
            start, end = int(start_text), int(end_text)
            if start > end:
                start, end = end, start
            indexes.extend(range(start - 1, end))
        elif part.isdigit():
            indexes.append(int(part) - 1)
    return sorted({i for i in indexes if 0 <= i < max_index})


def read_interactive_key() -> str:
    """读取一个交互按键，归一化为 up/down/space/enter/escape。"""
    if sys.platform == "win32":
        import msvcrt

        char = msvcrt.getwch()
        if char in ("\x00", "\xe0"):
            key = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(key, "")
        return {
            "\r": "enter",
            " ": "space",
            "\x1b": "escape",
            "\x01": "all",
            "j": "down",
            "k": "up",
        }.get(char.lower(), char.lower())

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if char == "\x1b":
            rest = sys.stdin.read(2)
            if rest == "[A":
                return "up"
            if rest == "[B":
                return "down"
            return "escape"
        return {
            "\r": "enter",
            "\n": "enter",
            " ": "space",
            "\x01": "all",
            "j": "down",
            "k": "up",
        }.get(char.lower(), char.lower())
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def choose_project_skills_numbered(skills: list[Path], agents_dir: Path, project_dir: Path) -> list[Path]:
    """非 TTY 环境下的编号选择 fallback。"""
    print(f"{CYAN}Target project:{NC} {BOLD}{project_dir}{NC}")
    print(f"{CYAN}Available skills:{NC}\n")
    for index, skill_dir in enumerate(skills, start=1):
        mark = f"{GREEN}✓{NC}" if project_skill_present(agents_dir / skill_dir.name) else " "
        desc = shorten(read_description(skill_dir))
        print(f"  {YELLOW}{index:2d}){NC} {mark} {BOLD}{skill_dir.name:<36}{NC} {DIM}{desc}{NC}")

    print("")
    print(f"{CYAN}输入编号安装（如 1 3 5 或 1-4），输入 a 全选，直接回车退出：{NC}", end="")
    selection = input().strip()
    if not selection:
        return []
    if selection.lower() == "a":
        return skills
    indexes = parse_selection(selection, len(skills))
    return [skills[i] for i in indexes]


def render_skill_picker(skills: list[Path], agents_dir: Path, selected: set[int], cursor: int, project_dir: Path) -> None:
    """渲染空格多选界面。"""
    print("\033[2J\033[H", end="")
    print(f"{CYAN}Target project:{NC} {BOLD}{project_dir}{NC}")
    print(f"{CYAN}选择 Skills：{NC}{DIM}↑/↓ 或 j/k 移动，Space 勾选，Ctrl-A 全选/取消，Enter 确认，Esc 退出{NC}\n")
    for index, skill_dir in enumerate(skills):
        installed = project_skill_present(agents_dir / skill_dir.name)
        pointer = f"{CYAN}>{NC}" if index == cursor else " "
        checkbox = f"{GREEN}[x]{NC}" if index in selected else "[ ]"
        installed_tag = f" {YELLOW}(installed){NC}" if installed else ""
        desc = shorten(read_description(skill_dir))
        line_style = BOLD if index == cursor else ""
        print(f"{pointer} {checkbox} {line_style}{skill_dir.name:<36}{NC}{installed_tag} {DIM}{desc}{NC}")


def choose_project_skills(project_dir: Path) -> list[Path]:
    """交互式选择要安装到项目的技能。"""
    skills = select_skills(None)
    agents_dir = project_dir / ".agents" / "skills"
    if not sys.stdin.isatty():
        return choose_project_skills_numbered(skills, agents_dir, project_dir)

    selected = {index for index, skill_dir in enumerate(skills) if project_skill_present(agents_dir / skill_dir.name)}
    cursor = 0
    while True:
        render_skill_picker(skills, agents_dir, selected, cursor, project_dir)
        key = read_interactive_key()
        if key == "up":
            cursor = (cursor - 1) % len(skills)
        elif key == "down":
            cursor = (cursor + 1) % len(skills)
        elif key == "space":
            if cursor in selected:
                selected.remove(cursor)
            else:
                selected.add(cursor)
        elif key == "all":
            selected = set() if len(selected) == len(skills) else set(range(len(skills)))
        elif key == "enter":
            print("\033[2J\033[H", end="")
            return [skills[index] for index in sorted(selected)]
        elif key == "escape":
            print("\033[2J\033[H", end="")
            return []


def target_dirs(target: str) -> list[Path]:
    """返回目标平台的技能目录列表。"""
    mapping = {
        "claude": [CLAUDE_SKILLS],
        "codex":  [CODEX_SKILLS],
        "both":   [d for d in (CLAUDE_SKILLS, CODEX_SKILLS)],
    }
    return mapping.get(target, [CLAUDE_SKILLS, CODEX_SKILLS])


def install_skills(skills: list[Path], targets: list[Path], do_pip: bool, force: bool = False) -> None:
    """安装技能到目标目录。"""
    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n{CYAN}==> Installing to {target_dir}{NC}")

        for skill_dir in skills:
            name = skill_dir.name
            link_path = target_dir / name

            # 已是正确的链接 → 跳过
            if is_symlink_or_junction(link_path) or link_path.is_symlink():
                current = read_symlink_target(link_path)
                if current and Path(current).resolve() == skill_dir.resolve():
                    print(f"  {GREEN}[OK]{NC} {name} (already linked)")
                    continue
                else:
                    print(f"  {YELLOW}[WARN]{NC} {name} linked to {current or '?'}, replacing...")
                    remove_link_or_junction(link_path)

            # 非链接的文件/目录 → 保护用户数据
            if link_path.exists():
                if force and link_path.is_dir() and (link_path / "SKILL.md").is_file():
                    shutil.rmtree(link_path)
                    print(f"  {YELLOW}[REPLACE]{NC} {name} existing fallback copy")
                elif force and link_path.is_file():
                    link_path.unlink()
                    print(f"  {YELLOW}[REPLACE]{NC} {name} existing file")
                else:
                    print(f"  {YELLOW}[SKIP]{NC} {name} — 目标路径已存在（非链接），跳过")
                    continue

            # 创建链接（或回退复制）
            op = link_or_copy(skill_dir, link_path)
            tag = "LINKED" if op == "linked" else f"COPIED ({op})"
            color = GREEN if op == "linked" else YELLOW
            print(f"  {color}[{tag}]{NC} {name} → {link_path}")

            # pip install
            req = skill_dir / "requirements.txt"
            if do_pip and req.is_file():
                print(f"    {CYAN}pip install -r {name}/requirements.txt...{NC}")
                if pip_install(req):
                    print(f"    {GREEN}[PIP OK]{NC}")
                else:
                    print(f"    {YELLOW}[PIP FAIL]{NC} 请手动执行: pip install -r {req}")


def uninstall_skills(skills: list[Path], targets: list[Path]) -> None:
    """卸载技能（删除符号链接/回退副本）。"""
    for target_dir in targets:
        if not target_dir.is_dir():
            print(f"\n{CYAN}==> {target_dir} does not exist, skip.{NC}")
            continue
        print(f"\n{CYAN}==> Uninstalling from {target_dir}{NC}")

        for skill_dir in skills:
            name = skill_dir.name
            link_path = target_dir / name

            if is_symlink_or_junction(link_path) or link_path.is_symlink():
                remove_link_or_junction(link_path)
                print(f"  {GREEN}[REMOVED]{NC} {link_path}")
            elif link_path.is_dir():
                # 回退复制产生的真实目录 — 需要判断是否为回退方案
                # 简单启发：如果目录名匹配且内部有 SKILL.md，认为是回退副本
                if (link_path / "SKILL.md").is_file():
                    shutil.rmtree(link_path)
                    print(f"  {GREEN}[REMOVED]{NC} {link_path} (was a fallback copy)")
                else:
                    print(f"  {YELLOW}[SKIP]{NC} {link_path} — 非安装工具创建，跳过")
            elif link_path.exists():
                print(f"  {YELLOW}[SKIP]{NC} {link_path} — 非链接，请手动删除")
            else:
                print(f"  {GREEN}[NONE]{NC} {name} 未安装")


def ensure_gitignore_entries(project_dir: Path, entries: list[str]) -> None:
    """将本地 agent 目录加入项目 .gitignore。"""
    git = shutil.which("git")
    if git:
        result = subprocess.run(
            [git, "-C", str(project_dir), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return
    else:
        return

    gitignore = project_dir / ".gitignore"
    existing = set()
    if gitignore.exists():
        existing = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    missing = [entry for entry in entries if entry not in existing]
    if not missing:
        print(f"  {YELLOW}[OK]{NC} .gitignore already contains local agent dirs")
        return
    with gitignore.open("a", encoding="utf-8") as handle:
        if gitignore.exists() and gitignore.stat().st_size > 0:
            handle.write("\n")
        for entry in missing:
            handle.write(f"{entry}\n")
    print(f"  {GREEN}[OK]{NC} .gitignore added: {', '.join(missing)}")


def ensure_claude_project_link(project_dir: Path, agents_dir: Path) -> None:
    """为 Claude Code 建立项目级 .claude/skills 指向 .agents/skills。"""
    claude_dir = project_dir / ".claude"
    claude_skills = claude_dir / "skills"
    claude_dir.mkdir(parents=True, exist_ok=True)

    if is_symlink_or_junction(claude_skills) or claude_skills.is_symlink():
        current = read_symlink_target(claude_skills)
        if current in {"../.agents/skills", ".agents/skills"}:
            print(f"  {YELLOW}[OK]{NC} .claude/skills already linked")
            return
        remove_link_or_junction(claude_skills)
    elif claude_skills.exists():
        print(f"  {YELLOW}[SKIP]{NC} .claude/skills exists; not modified")
        return

    if CAN_SYMLINK:
        os.symlink("../.agents/skills", str(claude_skills), target_is_directory=True)
        print(f"  {GREEN}[LINKED]{NC} .claude/skills -> ../.agents/skills")
        return

    op = link_or_copy(agents_dir, claude_skills)
    print(f"  {YELLOW}[{op.upper()}]{NC} .claude/skills")


def install_project_skills(skills: list[Path], project_dir: Path, force: bool = False) -> None:
    """安装技能到当前项目的 .agents/skills。"""
    agents_dir = project_dir / ".agents" / "skills"
    agents_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{CYAN}==> Installing to project {agents_dir}{NC}")

    for skill_dir in skills:
        dest = agents_dir / skill_dir.name
        if is_symlink_or_junction(dest) or dest.is_symlink():
            current = read_symlink_target(dest)
            if current and Path(current).resolve() == skill_dir.resolve():
                print(f"  {YELLOW}[OK]{NC} {skill_dir.name} already installed")
                continue
            remove_link_or_junction(dest)
        elif dest.exists():
            if force and dest.is_dir() and (dest / "SKILL.md").is_file():
                shutil.rmtree(dest)
                print(f"  {YELLOW}[REPLACE]{NC} {skill_dir.name} existing fallback copy")
            else:
                print(f"  {YELLOW}[SKIP]{NC} {skill_dir.name} exists; not modified")
                continue

        op = link_or_copy(skill_dir, dest)
        tag = "LINKED" if op == "linked" else op.upper()
        print(f"  {GREEN if op == 'linked' else YELLOW}[{tag}]{NC} {skill_dir.name}")

    ensure_claude_project_link(project_dir, agents_dir)
    ensure_gitignore_entries(project_dir, [".agents", ".claude"])


def uninstall_project_skills(skills: list[Path], project_dir: Path) -> None:
    """卸载当前项目 .agents/skills 下的技能。"""
    agents_dir = project_dir / ".agents" / "skills"
    print(f"\n{CYAN}==> Uninstalling from project {agents_dir}{NC}")
    if not agents_dir.is_dir():
        print(f"  {YELLOW}[MISSING]{NC} project skills directory does not exist")
        return

    for skill_dir in skills:
        dest = agents_dir / skill_dir.name
        if is_symlink_or_junction(dest) or dest.is_symlink():
            remove_link_or_junction(dest)
            print(f"  {GREEN}[REMOVED]{NC} {skill_dir.name}")
        elif dest.is_dir() and (dest / "SKILL.md").is_file():
            shutil.rmtree(dest)
            print(f"  {GREEN}[REMOVED]{NC} {skill_dir.name} (was a fallback copy)")
        elif dest.exists():
            print(f"  {YELLOW}[SKIP]{NC} {skill_dir.name} exists but is not a managed skill entry")
        else:
            print(f"  {GREEN}[NONE]{NC} {skill_dir.name} 未安装")


def status_skills(targets: list[Path]) -> None:
    """显示各目标平台下的技能安装状态。"""
    available = {d.name for d in select_skills(None)}
    for target_dir in targets:
        print(f"\n{CYAN}==> {target_dir}{NC}")
        if not target_dir.is_dir():
            print(f"  {YELLOW}[MISSING]{NC} target directory does not exist")
            continue
        installed = []
        for path in sorted(target_dir.iterdir()):
            if path.name in available:
                kind = "link" if is_symlink_or_junction(path) or path.is_symlink() else "copy"
                installed.append((path.name, kind))
        if not installed:
            print(f"  {YELLOW}[EMPTY]{NC} no known skills installed")
            continue
        for name, kind in installed:
            color = GREEN if kind == "link" else YELLOW
            print(f"  {color}{name:<30}{NC} {kind}")


def git_pull_repo() -> bool:
    """更新当前仓库，成功或无 Git 仓库时返回是否可继续安装。"""
    git = shutil.which("git")
    if not git:
        print(f"{YELLOW}[WARN] git not found in PATH; skip repository update.{NC}")
        return True
    result = subprocess.run([git, "-C", str(REPO_DIR), "pull", "--ff-only"])
    if result.returncode != 0:
        print(f"{RED}[FAIL] git pull --ff-only failed; fix the repository state and retry.{NC}")
        return False
    return True


def run_checked(command: list[str], cwd: Path | None = None) -> bool:
    """运行命令并返回是否成功。"""
    result = subprocess.run(command, cwd=str(cwd) if cwd else None)
    return result.returncode == 0


def load_skills_manifest() -> dict:
    """读取 skills-manifest.json。"""
    if not MANIFEST.exists():
        print(f"{YELLOW}[WARN] skills-manifest.json not found; skip upstream update.{NC}")
        return {"skills": {}}
    return json.loads(MANIFEST.read_text(encoding="utf-8-sig"))


def save_skills_manifest(manifest: dict) -> None:
    """写回 skills-manifest.json。"""
    manifest["updated"] = date.today().isoformat()
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def ensure_manifest_entries() -> bool:
    """为本地新增 skill 自动补充 manifest 条目。"""
    manifest = load_skills_manifest()
    entries = manifest.setdefault("skills", {})
    changed = False
    for skill_dir in select_skills(None):
        if skill_dir.name in entries:
            continue
        entries[skill_dir.name] = {
            "type": "custom",
            "source": None,
            "update": "local",
            "notes": "localagentskills update 自动登记；请按需补充来源和同步策略。",
        }
        print(f"{GREEN}[MANIFEST]{NC} added local skill: {skill_dir.name}")
        changed = True
    if changed:
        save_skills_manifest(manifest)
    return True


def normalize_skill_name(name: str) -> str:
    """归一化 skill 名，用于匹配上游目录和 frontmatter。"""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def read_skill_name(skill_md: Path) -> str:
    """读取 SKILL.md frontmatter name。"""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    for line in parts[1].splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def find_upstream_skill_dir(repo_dir: Path, skill_name: str) -> Path | None:
    """在上游仓库中定位某个 skill 的目录。"""
    candidates = [
        repo_dir / "skills" / skill_name,
        repo_dir / skill_name,
        repo_dir / skill_name.replace("-", "_"),
        repo_dir,
    ]
    for candidate in candidates:
        if (candidate / "SKILL.md").is_file():
            return candidate

    wanted = normalize_skill_name(skill_name)
    for skill_md in repo_dir.rglob("SKILL.md"):
        parent = skill_md.parent
        if normalize_skill_name(parent.name) == wanted:
            return parent
        frontmatter_name = read_skill_name(skill_md)
        if normalize_skill_name(frontmatter_name) == wanted:
            return parent
    return None


def replace_skill_from_upstream(skill_name: str, upstream_dir: Path) -> None:
    """用上游 skill 目录替换本地 skill。"""
    dest = SKILLS_DIR / skill_name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        upstream_dir,
        dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"),
    )


def sync_github_skills(skill_filter: list[str] | None = None) -> bool:
    """根据 manifest 直接从 GitHub 最新内容同步到本地 skills/。"""
    git = shutil.which("git")
    if not git:
        print(f"{YELLOW}[WARN] git not found in PATH; skip online skill sync.{NC}")
        return True

    manifest = load_skills_manifest().get("skills", {})
    wanted = set(skill_filter or [])
    by_source: dict[str, list[str]] = {}
    for skill_name, meta in sorted(manifest.items()):
        if wanted and skill_name not in wanted:
            continue
        source = meta.get("source")
        if isinstance(source, str) and "github.com" in source:
            by_source.setdefault(source, []).append(skill_name)

    ok = True
    with tempfile.TemporaryDirectory(prefix="localagentskills-update-") as temp:
        temp_dir = Path(temp)
        for index, (source, skill_names) in enumerate(sorted(by_source.items()), start=1):
            repo_dir = temp_dir / f"repo-{index}"
            print(f"{CYAN}==> Clone latest upstream {source}{NC}")
            if not run_checked([git, "clone", "--depth", "1", source, str(repo_dir)]):
                ok = False
                continue
            for skill_name in skill_names:
                upstream_skill = find_upstream_skill_dir(repo_dir, skill_name)
                if upstream_skill is None:
                    print(f"{YELLOW}[SKIP]{NC} {skill_name}: cannot locate SKILL.md in upstream")
                    ok = False
                    continue
                replace_skill_from_upstream(skill_name, upstream_skill)
                print(f"  {GREEN}[SYNCED]{NC} {skill_name} <- {upstream_skill.relative_to(repo_dir)}")
    return ok


def regenerate_readme_and_audit() -> bool:
    """重新生成 README 表格并运行审计。"""
    generator = REPO_DIR / "scripts" / "generate-readme.py"
    auditor = REPO_DIR / "scripts" / "audit-skills.py"
    ok = True
    if generator.exists():
        print(f"{CYAN}==> Regenerate README skill table{NC}")
        ok &= run_checked([sys.executable, str(generator)], REPO_DIR)
    else:
        print(f"{YELLOW}[WARN] scripts/generate-readme.py not found.{NC}")
    if auditor.exists():
        print(f"{CYAN}==> Audit skills metadata{NC}")
        ok &= run_checked([sys.executable, str(auditor)], REPO_DIR)
    else:
        print(f"{YELLOW}[WARN] scripts/audit-skills.py not found.{NC}")
    return ok


def update_repository_and_resources(args: argparse.Namespace) -> bool:
    """更新仓库、在线 skill 内容、manifest 和 README 文档。"""
    ok = True
    if not args.no_pull:
        ok &= git_pull_repo()
        if not ok:
            return False
    ok &= ensure_manifest_entries()
    if not args.no_sync:
        ok &= sync_github_skills(args.skills or None)
        ok &= ensure_manifest_entries()
    if not args.no_readme:
        ok &= regenerate_readme_and_audit()
    return ok


# ── 入口 ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="localagentskills",
        description="跨平台管理 localagentskills 到 Claude Code / Codex",
    )
    parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                        help=argparse.SUPPRESS)
    parser.add_argument("--skill", action="append", default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--pip", dest="do_pip", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--list", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--uninstall", action="store_true",
                        help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(dest="command")

    def add_global_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("skills", nargs="*", help="技能名；省略则处理全部技能")
        subparser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                               help="目标平台 (default: both)")

    install_parser = subparsers.add_parser("install", help="安装技能到当前项目")
    install_parser.add_argument("skills", nargs="*", help="技能名；省略则进入空格多选界面")
    install_parser.add_argument("--project", default=".", help="目标项目目录 (default: 当前目录)")
    install_parser.add_argument("--all", action="store_true", help="安装全部技能到项目")
    install_parser.add_argument("--global", dest="global_install", action="store_true",
                                help="安装到全局 Claude/Codex 技能目录")
    install_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                                help="配合 --global 使用的目标平台 (default: both)")
    install_parser.add_argument("--pip", dest="do_pip", action="store_true",
                                help="配合 --global 使用，同时安装 requirements.txt")
    install_parser.add_argument("--force", action="store_true",
                                help="替换已存在的回退副本")

    update_parser = subparsers.add_parser("update", help="更新仓库、在线 skill 内容、manifest 和 README")
    update_parser.add_argument("skills", nargs="*", help="只同步指定 skill；省略则同步全部 GitHub 来源")
    update_parser.add_argument("--no-pull", action="store_true",
                               help="跳过当前仓库 git pull")
    update_parser.add_argument("--no-sync", "--no-upstreams", action="store_true",
                               help="跳过在线 GitHub skill 同步")
    update_parser.add_argument("--no-readme", action="store_true",
                               help="跳过 README 生成和审计")

    uninstall_parser = subparsers.add_parser("uninstall", help="卸载当前项目中的技能")
    uninstall_parser.add_argument("skills", nargs="*", help="技能名；省略则卸载当前项目里的全部技能")
    uninstall_parser.add_argument("--project", default=".", help="目标项目目录 (default: 当前目录)")
    uninstall_parser.add_argument("--global", dest="global_uninstall", action="store_true",
                                  help="卸载全局 Claude/Codex 技能目录中的技能")
    uninstall_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                                  help="配合 --global 使用的目标平台 (default: both)")

    status_parser = subparsers.add_parser("status", help="查看已安装技能")
    status_parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                               help="目标平台 (default: both)")

    subparsers.add_parser("list", help="列出仓库中的可用技能")
    args = parser.parse_args()

    if args.command == "list" or args.list:
        list_skills()
        return

    if args.command == "status":
        status_skills(target_dirs(args.target))
        return

    if args.command == "update":
        if update_repository_and_resources(args):
            print(f"\n{GREEN}Done.{NC}")
        else:
            print(f"\n{RED}Update finished with errors.{NC}")
            sys.exit(1)
        return

    if args.command == "install" and not args.global_install:
        project_dir = Path(args.project).expanduser().resolve()
        if args.all:
            skills = select_skills(None)
        elif args.skills:
            skills = select_skills(args.skills)
        else:
            skills = choose_project_skills(project_dir)
        if not skills:
            print(f"{YELLOW}未选择任何 skill，退出。{NC}")
            return
        install_project_skills(skills, project_dir, args.force)
        print(f"\n{GREEN}Done.{NC}")
        return

    legacy_uninstall = args.uninstall and args.command is None
    command = args.command or ("uninstall" if legacy_uninstall else "install")
    skill_names = getattr(args, "skills", None) or args.skill
    skills = select_skills(skill_names)
    if not skills:
        print(f"{YELLOW}No skills found in {SKILLS_DIR}{NC}")
        return

    targets = target_dirs(args.target)

    if command == "uninstall":
        if args.command == "uninstall" and not getattr(args, "global_uninstall", False):
            project_dir = Path(args.project).expanduser().resolve()
            uninstall_project_skills(skills, project_dir)
        else:
            uninstall_skills(skills, targets)
    else:
        if command == "update" and not args.no_pull and not git_pull_repo():
            return
        if not CAN_SYMLINK:
            print(f"{YELLOW}[WARN] 符号链接不可用（Windows 需管理员权限或开发者模式），将回退到复制。{NC}")
            print(f"{YELLOW}       回退复制不会自动同步上游更新，建议开启开发者模式后重试。{NC}")
        install_skills(skills, targets, getattr(args, "do_pip", False), getattr(args, "force", False))

    print(f"\n{GREEN}Done.{NC}")


if __name__ == "__main__":
    main()
