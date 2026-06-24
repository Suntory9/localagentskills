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

# ── 提取 SKILL.md 简短描述（≤55字符，按词截断）──────────────────────────────
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
# 取第一句（中文句号或英文 ". "）
for sep in ["。", ". "]:
    pos = desc.find(sep, 5)
    if 5 < pos < 80:
        desc = desc[:pos + len(sep)].strip()
        break
# 按词截断到 55 字符
if len(desc) > 55:
    cut = desc[:55].rfind(" ")
    desc = desc[:cut if cut > 20 else 55] + "…"
print(desc)
PY
}

# ── 构建带已安装标记的列表（已安装排前面）────────────────────────────────────
build_fzf_list() {
  local skill desc tag
  # 已安装的先输出
  while IFS= read -r skill; do
    [ -e "$AGENTS_DIR/$skill" ] || continue
    desc=$(skill_desc "$skill")
    printf "%s\t%s\n" "$skill" "$desc"
  done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)
  # 未安装的后输出
  while IFS= read -r skill; do
    [ -e "$AGENTS_DIR/$skill" ] && continue
    desc=$(skill_desc "$skill")
    printf "%s\t%s\n" "$skill" "$desc"
  done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)
}

# ── fzf 多选，已安装项预勾选 ──────────────────────────────────────────────────
select_skills_fzf() {
  # 统计已安装数量，用于生成预勾选 bind
  local n_installed=0 skill
  while IFS= read -r skill; do
    [ -e "$AGENTS_DIR/$skill" ] && n_installed=$((n_installed + 1))
  done < <(ls "$WAREHOUSE" | grep -v '^\.' | sort)

  # 构建 start bind：pos(1)+toggle+down+pos(2)+toggle+down...
  local start_bind="start:"
  if [ "$n_installed" -gt 0 ]; then
    for i in $(seq 1 "$n_installed"); do
      start_bind+="pos($i)+toggle+down+"
    done
    start_bind="${start_bind%+}"  # 去掉末尾多余的 +
  else
    start_bind+="pos(1)"
  fi

  build_fzf_list \
    | fzf --multi \
          --ansi \
          --delimiter='\t' \
          --with-nth='1,2' \
          --tabstop=4 \
          --prompt='> ' \
          --header='空格/Tab 勾选  Enter 确认  Ctrl-A 全选  / 搜索' \
          --bind="space:toggle+down" \
          --bind="$start_bind" \
          --no-preview \
          --color='header:italic,prompt:cyan,marker:green' \
          --marker='✓' \
    | cut -f1
}

# ── fallback numbered list（含简介，已安装标记）──────────────────────────────
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

  [ "$selection" = "a" ] && { printf '%s\n' "${skills[@]}"; return; }

  local num idx
  for num in $selection; do
    idx=$((num - 1))
    [ "$idx" -ge 0 ] && [ "$idx" -lt "${#skills[@]}" ] && echo "${skills[$idx]}"
  done
}

# ── 执行选择 ──────────────────────────────────────────────────────────────────
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

[ "${#SELECTED[@]}" -eq 0 ] && { echo -e "${YELLOW}未选择任何 skill，退出。${NC}"; exit 0; }

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

# ── .gitignore ────────────────────────────────────────────────────────────────
if git -C "$TARGET" rev-parse --git-dir &>/dev/null 2>&1; then
  GITIGNORE="$TARGET/.gitignore"
  added=()
  for entry in ".agents" ".claude"; do
    if ! grep -qxF "$entry" "$GITIGNORE" 2>/dev/null; then
      echo "$entry" >> "$GITIGNORE"
      added+=("$entry")
    fi
  done
  if [ "${#added[@]}" -gt 0 ]; then
    echo -e "  ${GREEN}✓ .gitignore${NC}（已添加：${added[*]}）"
  else
    echo -e "  ${YELLOW}↺ .gitignore${NC}（已包含，跳过）"
  fi
fi

echo ""
echo -e "${GREEN}${BOLD}完成！${NC} 已安装 ${#SELECTED[@]} 个 skill 到 ${BOLD}$TARGET${NC}"
