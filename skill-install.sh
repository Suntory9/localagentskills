#!/usr/bin/env bash
set -euo pipefail

WAREHOUSE="$(cd "$(dirname "$0")/skills" && pwd)"
TARGET="${1:-}"

# ── 颜色 ──────────────────────────────────────────────────────────────────────
BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║       PersonalSkills Installer        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 目标项目目录 ──────────────────────────────────────────────────────────────
if [ -z "$TARGET" ]; then
  echo -e "${CYAN}目标项目目录${NC}（回车使用当前目录 $(pwd)）："
  read -r input
  TARGET="${input:-$(pwd)}"
fi
TARGET="$(cd "$TARGET" && pwd)"
echo -e "  → ${BOLD}$TARGET${NC}"
echo ""

# ── 读取可用 skill 列表 ───────────────────────────────────────────────────────
mapfile -t ALL_SKILLS < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)

# ── 检测已安装的 skill ────────────────────────────────────────────────────────
AGENTS_DIR="$TARGET/.agents/skills"
installed() { [ -e "$AGENTS_DIR/$1" ] && echo " ✓" || echo "  "; }

# ── 选择界面：优先 fzf，否则 numbered list ────────────────────────────────────
select_skills_fzf() {
  printf '%s\n' "${ALL_SKILLS[@]}" \
    | fzf --multi \
          --prompt="空格多选，回车确认 > " \
          --header="↑↓ 移动  Tab/空格 选中  回车 确认  Ctrl-A 全选" \
          --preview="cat '$WAREHOUSE/{}/SKILL.md' 2>/dev/null | head -30" \
          --preview-window=right:50%:wrap
}

select_skills_list() {
  echo -e "${CYAN}可用 Skills：${NC}"
  for i in "${!ALL_SKILLS[@]}"; do
    mark=$(installed "${ALL_SKILLS[$i]}")
    printf "  ${YELLOW}%2d)${NC}%s %s\n" "$((i+1))" "$mark" "${ALL_SKILLS[$i]}"
  done
  echo ""
  echo -e "${CYAN}输入编号（空格分隔，如 1 3 5），输入 a 全选，回车确认：${NC}"
  read -r selection

  if [ "$selection" = "a" ]; then
    printf '%s\n' "${ALL_SKILLS[@]}"
    return
  fi

  for num in $selection; do
    idx=$((num - 1))
    if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#ALL_SKILLS[@]}" ]; then
      echo "${ALL_SKILLS[$idx]}"
    fi
  done
}

if command -v fzf &>/dev/null; then
  mapfile -t SELECTED < <(select_skills_fzf)
else
  mapfile -t SELECTED < <(select_skills_list)
fi

if [ "${#SELECTED[@]}" -eq 0 ]; then
  echo -e "${YELLOW}未选择任何 skill，退出。${NC}"
  exit 0
fi

# ── 安装 ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}正在安装到 $AGENTS_DIR ...${NC}"
mkdir -p "$AGENTS_DIR"

for skill in "${SELECTED[@]}"; do
  skill="$(echo "$skill" | tr -d '[:space:]')"   # strip whitespace from fzf output
  src="$WAREHOUSE/$skill"
  dest="$AGENTS_DIR/$skill"

  if [ ! -d "$src" ]; then
    echo -e "  ${RED}✗ $skill${NC}（warehouse 中不存在）"
    continue
  fi

  if [ -L "$dest" ]; then
    echo -e "  ${YELLOW}↺ $skill${NC}（已安装，跳过）"
  else
    ln -s "$src" "$dest"
    echo -e "  ${GREEN}✓ $skill${NC}"
  fi
done

# ── 创建 .claude/skills → .agents/skills ─────────────────────────────────────
CLAUDE_SKILLS="$TARGET/.claude/skills"
mkdir -p "$TARGET/.claude"

if [ -L "$CLAUDE_SKILLS" ] && [ "$(readlink "$CLAUDE_SKILLS")" = ".agents/skills" ]; then
  echo -e "\n  ${YELLOW}↺ .claude/skills${NC}（已正确链接，跳过）"
elif [ -e "$CLAUDE_SKILLS" ]; then
  echo -e "\n  ${YELLOW}⚠ .claude/skills 已存在且非预期链接，未修改${NC}"
else
  ln -s .agents/skills "$CLAUDE_SKILLS"
  echo -e "\n  ${GREEN}✓ .claude/skills → .agents/skills${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}完成！${NC} 已安装 ${#SELECTED[@]} 个 skill 到 $TARGET"
