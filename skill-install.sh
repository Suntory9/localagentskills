#!/usr/bin/env bash
set -euo pipefail

WAREHOUSE="$(cd "$(dirname "$0")/skills" && pwd)"
TARGET="${1:-}"

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; DIM='\033[2m'; NC='\033[0m'

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
echo -e "  → ${BOLD}$TARGET${NC}\n"

AGENTS_DIR="$TARGET/.agents/skills"

# ── 提取 SKILL.md description 首句 ───────────────────────────────────────────
skill_desc() {
  local skill_md="$WAREHOUSE/$1/SKILL.md"
  [ -f "$skill_md" ] || { echo "—"; return; }
  python3 - "$skill_md" <<'PY'
import sys, re
text = open(sys.argv[1]).read()
m = re.search(r"^description:\s*>-?\s*\n((?:  .+\n)+)", text, re.M)
if m:
    desc = re.sub(r"\s+", " ", m.group(1)).strip()
else:
    m2 = re.search(r"^description:\s*(.+)", text, re.M)
    desc = m2.group(1).strip() if m2 else "—"
end = desc.find("。")
if end == -1: end = desc.find(". ", 10)
if end != -1: desc = desc[:end+1]
print(desc[:100])
PY
}

# ── 读取所有 skill 名称到数组（兼容 bash 3.2）────────────────────────────────
read_skills_array() {
  local -n _arr=$1
  _arr=()
  while IFS= read -r s; do
    _arr+=("$s")
  done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)
}

# ── fzf 多选（名称 + 简介）───────────────────────────────────────────────────
select_skills_fzf() {
  local skill desc
  while IFS= read -r skill; do
    desc=$(skill_desc "$skill")
    printf "%s\t%s\n" "$skill" "$desc"
  done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort) \
    | fzf --multi \
          --ansi \
          --delimiter='\t' \
          --with-nth='1,2' \
          --tabstop=4 \
          --prompt='> ' \
          --header='Tab 多选  Enter 确认  Ctrl-A 全选  / 搜索' \
          --preview="cat '$WAREHOUSE/{1}/SKILL.md' 2>/dev/null | head -40" \
          --preview-window='right:50%:wrap' \
          --color='header:italic,prompt:cyan' \
    | cut -f1
}

# ── fallback numbered list（含简介）─────────────────────────────────────────
select_skills_list() {
  local skills=() skill desc mark i
  while IFS= read -r s; do skills+=("$s"); done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)

  echo -e "${CYAN}可用 Skills：${NC}\n"
  for i in "${!skills[@]}"; do
    skill="${skills[$i]}"
    mark="  "
    [ -e "$AGENTS_DIR/$skill" ] && mark="${GREEN}✓ ${NC}"
    desc=$(skill_desc "$skill")
    printf "  ${YELLOW}%2d)${NC} %b${BOLD}%-36s${NC} ${DIM}%s${NC}\n" \
      "$((i+1))" "$mark" "$skill" "$desc"
  done

  echo ""
  echo -e "${CYAN}输入编号（空格分隔，如 1 3 5），a 全选，回车确认：${NC}"
  read -r selection

  if [ "$selection" = "a" ]; then
    printf '%s\n' "${skills[@]}"
    return
  fi

  local num idx
  for num in $selection; do
    idx=$((num - 1))
    if [ "$idx" -ge 0 ] && [ "$idx" -lt "${#skills[@]}" ]; then
      echo "${skills[$idx]}"
    fi
  done
}

# ── 执行选择（结果存入 SELECTED 数组）────────────────────────────────────────
SELECTED=()
if command -v fzf &>/dev/null; then
  while IFS= read -r line; do
    [ -n "$line" ] && SELECTED+=("$line")
  done < <(select_skills_fzf)
else
  while IFS= read -r line; do
    [ -n "$line" ] && SELECTED+=("$line")
  done < <(select_skills_list)
fi

if [ "${#SELECTED[@]}" -eq 0 ]; then
  echo -e "${YELLOW}未选择任何 skill，退出。${NC}"
  exit 0
fi

# ── 安装软链接 ────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}正在安装到 $AGENTS_DIR ...${NC}"
mkdir -p "$AGENTS_DIR"

for skill in "${SELECTED[@]}"; do
  skill="$(echo "$skill" | xargs)"
  src="$WAREHOUSE/$skill"
  dest="$AGENTS_DIR/$skill"
  if [ ! -d "$src" ]; then
    echo -e "  ${RED}✗ $skill${NC}（不存在）"
  elif [ -L "$dest" ]; then
    echo -e "  ${YELLOW}↺ $skill${NC}（已安装，跳过）"
  else
    ln -s "$src" "$dest"
    echo -e "  ${GREEN}✓ $skill${NC}"
  fi
done

# ── .claude/skills → .agents/skills ──────────────────────────────────────────
CLAUDE_SKILLS="$TARGET/.claude/skills"
mkdir -p "$TARGET/.claude"

if [ -L "$CLAUDE_SKILLS" ] && [ "$(readlink "$CLAUDE_SKILLS")" = ".agents/skills" ]; then
  echo -e "  ${YELLOW}↺ .claude/skills${NC}（已链接，跳过）"
elif [ -e "$CLAUDE_SKILLS" ]; then
  echo -e "  ${YELLOW}⚠ .claude/skills 已存在，未修改${NC}"
else
  ln -s .agents/skills "$CLAUDE_SKILLS"
  echo -e "  ${GREEN}✓ .claude/skills → .agents/skills${NC}"
fi

echo ""
echo -e "${GREEN}${BOLD}完成！${NC} 已安装 ${#SELECTED[@]} 个 skill 到 ${BOLD}$TARGET${NC}"
