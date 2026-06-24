#!/bin/zsh
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: submit_issue_fix.sh <jira-url-or-key> <repo-path> [branch] [file ...] [--dry-run]" >&2
  exit 1
fi

issue_input="$1"
repo_path="$2"
shift 2

branch="2023-11-28-Unity2021-3-13"
dry_run=0
files=()
branch_set=0

for arg in "$@"; do
  if [[ "$arg" == "--dry-run" ]]; then
    dry_run=1
  elif [[ $branch_set -eq 0 ]]; then
    branch="$arg"
    branch_set=1
  else
    files+=("$arg")
  fi
done

skill_dir="${0:A:h}"
issue_json="$("$skill_dir/read_issue.sh" "$issue_input")"

commit_msg="$(ISSUE_JSON="$issue_json" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["ISSUE_JSON"])
print(f'{data["key"]}{data["fields"]["summary"]}')
PY
)"

run_cmd() {
  echo "+ $*"
  if [[ $dry_run -eq 0 ]]; then
    "$@"
  fi
}

if [[ ! -d "$repo_path/.git" ]]; then
  echo "Not a git repository: $repo_path" >&2
  exit 2
fi

current_branch="$(git -C "$repo_path" branch --show-current)"
if [[ "$current_branch" != "$branch" ]]; then
  if [[ -n "$(git -C "$repo_path" status --porcelain)" ]]; then
    echo "Refusing to checkout $branch because the worktree is dirty on $current_branch" >&2
    exit 3
  fi
  run_cmd git -C "$repo_path" checkout "$branch"
fi

run_cmd git -C "$repo_path" fetch origin
run_cmd git -C "$repo_path" pull origin "$branch"

if (( ${#files[@]} > 0 )); then
  for file in "${files[@]}"; do
    run_cmd git -C "$repo_path" add "$file"
  done
fi

if [[ $dry_run -eq 0 ]]; then
  if [[ -z "$(git -C "$repo_path" diff --cached --name-only)" ]]; then
    echo "No staged changes found. Pass explicit files or stage changes before running this script." >&2
    exit 4
  fi
else
  if (( ${#files[@]} == 0 )) && [[ -z "$(git -C "$repo_path" diff --cached --name-only)" ]]; then
    echo "Dry-run found no explicit files and no staged changes." >&2
    exit 4
  fi
fi

run_cmd git -C "$repo_path" commit -m "$commit_msg"
run_cmd git -C "$repo_path" push origin "$branch"

echo "commit_message=$commit_msg"
