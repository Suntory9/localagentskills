#!/bin/zsh
set -euo pipefail

source ~/.zshrc >/dev/null 2>&1 || true

if [[ $# -lt 1 ]]; then
  echo "Usage: read_issue.sh <jira-url-or-key>" >&2
  exit 1
fi

if [[ -z "${ATLASSIAN_EMAIL:-}" || -z "${ATLASSIAN_API_TOKEN:-}" ]]; then
  echo "Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc" >&2
  exit 2
fi

issue_input="$1"
issue_key="$issue_input"

if [[ "$issue_input" =~ '(TTDBL-[0-9]+)' ]]; then
  issue_key="${match[1]}"
fi

curl -sS \
  -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
  "https://xindong.atlassian.net/rest/api/3/issue/${issue_key}?fields=summary,description,status,assignee,reporter,comment"
