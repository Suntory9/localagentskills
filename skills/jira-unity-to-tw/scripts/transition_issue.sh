#!/bin/zsh
set -euo pipefail

source ~/.zshrc >/dev/null 2>&1 || true

if [[ $# -lt 2 ]]; then
  echo "Usage: transition_issue.sh <jira-url-or-key-or-number> <target-status-name> [test-case-comment]" >&2
  exit 1
fi

if [[ -z "${ATLASSIAN_EMAIL:-}" || -z "${ATLASSIAN_API_TOKEN:-}" ]]; then
  echo "Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc" >&2
  exit 2
fi

issue_input="$1"
target_status="$2"
shift 2
test_case_comment="$*"
issue_key="$issue_input"

if [[ "$issue_input" =~ '(TTDBL-[0-9]+)' ]]; then
  issue_key="${match[1]}"
elif [[ "$issue_input" =~ '^[0-9]+$' ]]; then
  issue_key="TTDBL-${issue_input}"
fi

base_url="https://xindong.atlassian.net/rest/api/3/issue/${issue_key}"

current_json="$(curl --fail-with-body -sS \
  -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
  -H 'Accept: application/json' \
  "${base_url}?fields=status")"

initial_status="$(ISSUE_JSON="$current_json" python3 - <<'PY'
import json
import os
print(json.loads(os.environ["ISSUE_JSON"])["fields"]["status"]["name"])
PY
)"

steps=()
workflow_statuses=(
  "待验收"
  "主干测试"
  "待合并"
  "开发服待测试"
  "开发服测试中"
)

while true; do
  current_status="$(ISSUE_JSON="$current_json" python3 - <<'PY'
import json
import os
print(json.loads(os.environ["ISSUE_JSON"])["fields"]["status"]["name"])
PY
)"

  if [[ "$current_status" == "$target_status" ]]; then
    break
  fi

  transitions_json="$(curl --fail-with-body -sS \
    -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
    -H 'Accept: application/json' \
    "${base_url}/transitions?expand=transitions.fields")"

  transition_result="$(ISSUE_JSON="$current_json" TRANSITIONS_JSON="$transitions_json" TARGET_STATUS="$target_status" WORKFLOW_STATUSES="${(j:|:)workflow_statuses}" python3 - <<'PY'
import json
import os
import sys

issue = json.loads(os.environ["ISSUE_JSON"])
transitions = json.loads(os.environ["TRANSITIONS_JSON"]).get("transitions", [])
target = os.environ["TARGET_STATUS"]
workflow_statuses = [item for item in os.environ.get("WORKFLOW_STATUSES", "").split("|") if item]
current_status = issue["fields"]["status"]["name"]

def build_payload(item):
    payload = {"transition": {"id": item["id"]}}
    fields = item.get("fields", {})
    process_field = fields.get("customfield_11277")
    if process_field:
        for value in process_field.get("allowedValues", []):
            if value.get("value") == "BUG 已修复":
                payload["fields"] = {"customfield_11277": {"id": value["id"]}}
                break
    return payload

def emit(mode, item):
    payload = build_payload(item)
    destination = item.get("to", {}).get("name", item["name"])
    print(f"{mode}\t{item['id']}\t{destination}\t{json.dumps(payload, ensure_ascii=False)}")
    sys.exit(0)

for item in transitions:
    transition_name = item["name"]
    destination = item.get("to", {}).get("name", transition_name)
    if transition_name == target or destination == target:
        emit("direct", item)

if current_status in workflow_statuses and target in workflow_statuses:
    current_index = workflow_statuses.index(current_status)
    target_index = workflow_statuses.index(target)
    if current_index < target_index:
        next_expected = workflow_statuses[current_index + 1]
        for item in transitions:
            destination = item.get("to", {}).get("name", item["name"])
            if destination == next_expected:
                emit("path", item)

if len(transitions) == 1:
    emit("auto", transitions[0])

print(f"Current status: {current_status}", file=sys.stderr)
if transitions:
    print("Available transitions:", file=sys.stderr)
    for item in transitions:
        destination = item.get("to", {}).get("name", item["name"])
        print(f"- {item['name']} -> {destination} ({item['id']})", file=sys.stderr)
else:
    print("No available transitions.", file=sys.stderr)
sys.exit(3)
PY
)"

  transition_id="$(printf '%s\n' "$transition_result" | cut -f2)"
  transition_name="$(printf '%s\n' "$transition_result" | cut -f3)"
  transition_payload="$(printf '%s\n' "$transition_result" | cut -f4-)"

  curl --fail-with-body -sS \
    -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
    -H 'Accept: application/json' \
    -H 'Content-Type: application/json' \
    -X POST \
    --data "$transition_payload" \
    "${base_url}/transitions" >/dev/null

  steps+=("${current_status}->${transition_name}")

  current_json="$(curl --fail-with-body -sS \
    -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
    -H 'Accept: application/json' \
    "${base_url}?fields=status")"
done

final_status="$(ISSUE_JSON="$current_json" python3 - <<'PY'
import json
import os
data = json.loads(os.environ["ISSUE_JSON"])
print(data["fields"]["status"]["name"])
print(data["key"])
PY
)"

final_status_name="$(printf '%s\n' "$final_status" | sed -n '1p')"
final_issue_key="$(printf '%s\n' "$final_status" | sed -n '2p')"

comment_added=0
if [[ -n "$test_case_comment" ]]; then
  if [[ "$test_case_comment" != 测试用例：* ]]; then
    test_case_comment="测试用例：${test_case_comment}"
  fi

  comments_json="$(curl --fail-with-body -sS \
    -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
    -H 'Accept: application/json' \
    "${base_url}/comment?maxResults=100")"

  has_duplicate_comment="$(COMMENTS_JSON="$comments_json" TEST_CASE_COMMENT="$test_case_comment" python3 - <<'PY'
import difflib
import json
import os
import re


def adf_text(node):
    parts = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("type") == "text":
                parts.append(value.get("text", ""))
            attrs = value.get("attrs") or {}
            for key in ("text", "alt"):
                if attrs.get(key):
                    parts.append(str(attrs[key]))
            for child in value.get("content") or []:
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return "\n".join(x for x in parts if x)


def normalize(value):
    value = value.strip()
    if value.startswith("测试用例："):
        value = value.removeprefix("测试用例：")
    return re.sub(r"[\s，。；、,.!！?？:：；;（）()【】\[\]「」『』\"'`]+", "", value)


def similar(left, right):
    left_norm = normalize(left)
    right_norm = normalize(right)
    if not left_norm or not right_norm:
        return False
    if left_norm in right_norm or right_norm in left_norm:
        return True
    return difflib.SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.72


target = os.environ["TEST_CASE_COMMENT"]
comments = json.loads(os.environ["COMMENTS_JSON"]).get("comments", [])
for comment in comments:
    existing = adf_text(comment.get("body") or {}).strip()
    if existing.startswith("测试用例：") and similar(existing, target):
        print("1")
        break
else:
    print("0")
PY
)"

  if [[ "$has_duplicate_comment" == "1" ]]; then
    echo "skip_comment=similar_test_case_exists"
  else

    comment_payload="$(TEST_CASE_COMMENT="$test_case_comment" python3 - <<'PY'
import json
import os

text = os.environ["TEST_CASE_COMMENT"]
payload = {
    "body": {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                    }
                ],
            }
        ],
    }
}
print(json.dumps(payload, ensure_ascii=False))
PY
)"

    curl --fail-with-body -sS \
      -u "$ATLASSIAN_EMAIL:$ATLASSIAN_API_TOKEN" \
      -H 'Accept: application/json' \
      -H 'Content-Type: application/json' \
      -X POST \
      --data "$comment_payload" \
      "${base_url}/comment" >/dev/null
    comment_added=1
  fi
fi

echo "issue_key=${final_issue_key}"
echo "status_before=${initial_status}"
echo "status_after=${final_status_name}"
echo "target_status=${target_status}"
echo "comment_added=${comment_added}"
if (( ${#steps[@]} > 0 )); then
  echo "transition_path=${(j: | :)steps}"
fi
