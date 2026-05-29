#!/usr/bin/env python3
"""Personal Skills — 跨平台安装脚本 (macOS / Linux / Windows)

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
import os
import subprocess
import sys
import shutil
from pathlib import Path

# ── 跨平台常量 ────────────────────────────────────────────────

REPO_DIR = Path(__file__).resolve().parent
SKILLS_DIR = REPO_DIR / "skills"

# Claude Code / Codex 技能目录
CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
CODEX_SKILLS = Path.home() / ".codex" / "skills"

# ANSI 颜色（Windows 10+ 终端均支持）
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
RED = "\033[0;31m"
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
        os.symlink(str(src), str(dst))
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
            import _winapi
            _winapi.CreateJunction(str(path), str(path))
            return False
        except OSError:
            # 如果路径已存在且无法创建同名 junction，它可能已经是 junction
            return True
        except Exception:
            return False
    return False


def read_symlink_target(path: Path) -> str | None:
    """读取符号链接目标（跨平台）。"""
    try:
        return os.readlink(str(path))
    except OSError:
        return None


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
        in_front = False
        for line in text.splitlines():
            if line.strip() == "---":
                if not in_front:
                    in_front = True
                    continue
                else:
                    break
            if in_front and line.startswith("description:"):
                return line.split(":", 1)[1].strip()[:80]
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


def target_dirs(target: str) -> list[Path]:
    """返回目标平台的技能目录列表。"""
    mapping = {
        "claude": [CLAUDE_SKILLS],
        "codex":  [CODEX_SKILLS],
        "both":   [d for d in (CLAUDE_SKILLS, CODEX_SKILLS)],
    }
    return mapping.get(target, [CLAUDE_SKILLS, CODEX_SKILLS])


def install_skills(skills: list[Path], targets: list[Path], do_pip: bool) -> None:
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
                    link_path.unlink()

            # 非链接的文件/目录 → 保护用户数据
            if link_path.exists():
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
                link_path.unlink()
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


# ── 入口 ──────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="跨平台安装/卸载 Personal Skills 到 Claude Code / Codex",
    )
    parser.add_argument("--target", default="both", choices=["claude", "codex", "both"],
                        help="目标平台 (default: both)")
    parser.add_argument("--skill", action="append", default=None,
                        help="只安装指定技能（可重复使用）")
    parser.add_argument("--pip", dest="do_pip", action="store_true",
                        help="同时 pip install 每个技能的 requirements.txt")
    parser.add_argument("--list", action="store_true",
                        help="列出可用技能")
    parser.add_argument("--uninstall", action="store_true",
                        help="卸载（删除链接/副本）")
    args = parser.parse_args()

    # --list
    if args.list:
        list_skills()
        return

    skills = select_skills(args.skill)
    if not skills:
        print(f"{YELLOW}No skills found in {SKILLS_DIR}{NC}")
        return

    targets = target_dirs(args.target)

    if args.uninstall:
        uninstall_skills(skills, targets)
    else:
        if not CAN_SYMLINK:
            print(f"{YELLOW}[WARN] 符号链接不可用（Windows 需管理员权限或开发者模式），将回退到复制。{NC}")
            print(f"{YELLOW}       回退复制不会自动同步上游更新，建议开启开发者模式后重试。{NC}")
        install_skills(skills, targets, args.do_pip)

    print(f"\n{GREEN}Done.{NC}")


if __name__ == "__main__":
    main()
