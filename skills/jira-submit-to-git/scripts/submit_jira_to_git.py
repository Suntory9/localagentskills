#!/usr/bin/env python3
import argparse
import base64
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = "https://xindong.atlassian.net"
SKILL_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = SKILL_DIR / "config" / "repos.json"
WEEKLY_SCRIPT = SKILL_DIR / "scripts" / "update_weekly_report.py"


def run(cmd, cwd=None, check=True, capture=True, dry_run=False):
    printable = " ".join(str(x) for x in cmd)
    print(f"+ {printable}")
    if dry_run:
        return ""
    kwargs = {
        "cwd": cwd,
        "text": True,
        "check": False,
    }
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    result = subprocess.run([str(x) for x in cmd], **kwargs)
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        stdout = result.stdout.strip() if result.stdout else ""
        detail = stderr or stdout
        raise SystemExit(f"Command failed ({result.returncode}): {printable}\n{detail}")
    if capture:
        return result.stdout
    return ""


def load_shell_env():
    result = subprocess.run(
        ["zsh", "-lc", "source ~/.zshrc >/dev/null 2>&1 || true; env"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def normalize_issue_key(value):
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", value)
    if not match:
        raise SystemExit(f"Could not find Jira issue key in: {value}")
    return match.group(0)


def jira_auth_header():
    load_shell_env()
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        raise SystemExit("Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc")
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {"Authorization": f"Basic {encoded}", "Accept": "application/json", "Content-Type": "application/json"}


def jira_request(method, path, data=None):
    headers = jira_auth_header()
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE_URL + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Jira HTTP {exc.code}: {detail}") from exc


def read_issue(issue_key):
    fields = "summary,description,comment,attachment"
    return jira_request("GET", f"/rest/api/3/issue/{issue_key}?fields={urllib.parse.quote(fields)}")


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


def issue_text(issue):
    fields = issue.get("fields") or {}
    chunks = [fields.get("summary") or ""]
    chunks.append(adf_text(fields.get("description") or {}))
    comments = ((fields.get("comment") or {}).get("comments") or [])[-5:]
    for comment in comments:
        chunks.append(adf_text(comment.get("body") or {}))
    attachments = fields.get("attachment") or []
    chunks.extend(att.get("filename", "") for att in attachments)
    return "\n".join(chunks)


def build_jira_comment_body(body_text):
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": body_text}],
            }
        ],
    }


def comment_self_url(comment):
    self_url = comment.get("self") or ""
    marker = "/rest/api/3"
    if marker in self_url:
        return self_url.split(marker, 1)[1]
    comment_id = comment.get("id")
    if comment_id:
        return f"/rest/api/3/issue/{comment.get('issueId')}/comment/{comment_id}"
    return ""


def append_test_case_comment(issue_key, comment, existing, body_text, dry_run=False):
    combined = f"{existing}\n{body_text}"
    path = comment_self_url(comment)
    if not path:
        print(f"+ skip Jira comment update: cannot resolve comment path for {issue_key}")
        return
    print(f"+ update Jira comment: append {body_text}")
    if dry_run:
        return
    jira_request("PUT", path, {"body": build_jira_comment_body(combined)})


def add_jira_comment(issue_key, body_text, dry_run=False):
    if body_text.startswith("测试用例："):
        for comment in read_issue_comments(issue_key):
            existing = adf_text(comment.get("body") or {}).strip()
            if not existing.startswith("测试用例："):
                continue
            if is_similar_comment(existing, body_text):
                print(f"+ skip Jira comment: similar test-case comment already exists for {issue_key}")
                return
            append_test_case_comment(issue_key, comment, existing, body_text, dry_run=dry_run)
            return

    data = {"body": build_jira_comment_body(body_text)}
    print(f"+ add Jira comment: {body_text}")
    if dry_run:
        return
    jira_request("POST", f"/rest/api/3/issue/{issue_key}/comment", data)


def read_issue_comments(issue_key):
    comments = []
    start_at = 0
    while True:
        page = jira_request(
            "GET",
            f"/rest/api/3/issue/{issue_key}/comment?startAt={start_at}&maxResults=100",
        )
        page_comments = page.get("comments") or []
        comments.extend(page_comments)
        start_at += len(page_comments)
        if start_at >= page.get("total", 0) or not page_comments:
            return comments


def normalize_comment_text(value):
    value = value.strip()
    if value.startswith("测试用例："):
        value = value.removeprefix("测试用例：")
    return re.sub(r"[\s，。；、,.!！?？:：；;（）()【】\\[\\]「」『』\"'`]+", "", value)


def is_similar_comment(left, right):
    left_norm = normalize_comment_text(left)
    right_norm = normalize_comment_text(right)
    if not left_norm or not right_norm:
        return False
    if left_norm in right_norm or right_norm in left_norm:
        return True
    return difflib.SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.72


def is_duplicate_test_case_comment(issue_key, body_text):
    if not body_text.startswith("测试用例："):
        return False
    for comment in read_issue_comments(issue_key):
        existing = adf_text(comment.get("body") or {}).strip()
        if existing.startswith("测试用例：") and is_similar_comment(existing, body_text):
            return True
    return False


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["repos"]


def repo_root(path):
    root = run(["git", "rev-parse", "--show-toplevel"], cwd=path).strip()
    return str(Path(root).resolve())


def repo_config(root, configs):
    for configured, cfg in configs.items():
        if str(Path(configured).resolve()) == root:
            return cfg
    raise SystemExit(f"Unsupported repository: {root}")


def git_status_porcelain(root):
    output = run(["git", "status", "--porcelain=v1", "-z"], cwd=root)
    entries = output.split("\0")
    result = []
    for entry in entries:
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        result.append((status, path))
    return result


def staged_files(root):
    output = run(["git", "diff", "--cached", "--name-only", "-z"], cwd=root)
    return [x for x in output.split("\0") if x]


def file_diff_text(root, path):
    output = run(["git", "diff", "--", path], cwd=root, check=False)
    if not output:
        output = run(["git", "diff", "--cached", "--", path], cwd=root, check=False)
    return output[:20000]


def is_ignored(path, cfg):
    return any(path.startswith(prefix) for prefix in cfg.get("dirty_ignore_paths", []))


def is_temp_file(path):
    name = Path(path).name
    lower = name.lower()
    if lower.endswith((".log", ".tmp", ".bak", ".swp", ".DS_Store".lower())):
        return True
    if re.match(r"TTDBL-\d+.*\.md$", name):
        return True
    if lower.endswith(".md") and ("plan" in lower or "note" in lower):
        return True
    return False


def tokens_from_text(text):
    raw = re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)
    stop = {"the", "and", "for", "with", "this", "that", "Jira", "TTDBL"}
    return {x.lower() for x in raw if x not in stop}


def score_file(path, diff, tokens):
    lower_path = path.lower()
    lower_diff = diff.lower()
    score = 0
    for token in tokens:
        if len(token) < 3:
            continue
        if token in lower_path:
            score += 5
        if token in lower_diff:
            score += 2
    basename = Path(path).stem.lower()
    if basename and basename in tokens:
        score += 8
    if path.endswith((".lua", ".proto.txt", ".go", ".js", ".json")):
        score += 1
    return score


def infer_files(root, cfg, issue):
    staged = staged_files(root)
    if staged:
        return staged, [], "staged"

    status = git_status_porcelain(root)
    dirty = [path for _, path in status]
    ignored = [path for path in dirty if is_ignored(path, cfg)]
    candidates = [path for path in dirty if not is_ignored(path, cfg) and not is_temp_file(path)]
    excluded = [path for path in dirty if path not in candidates]

    if not candidates:
        raise SystemExit("No candidate files to submit after applying ignore rules.")

    if len(candidates) <= 8:
        return candidates, excluded, "small-dirty-set"

    tokens = tokens_from_text(issue_text(issue))
    scored = []
    for path in candidates:
        diff = file_diff_text(root, path)
        scored.append((score_file(path, diff, tokens), path))
    selected = [path for score, path in scored if score >= 5]
    if not selected:
        details = "\n".join(f"{score:>3} {path}" for score, path in sorted(scored, reverse=True)[:30])
        raise SystemExit(f"Low confidence file inference. Top candidates:\n{details}")
    return selected, excluded + [path for score, path in scored if path not in selected], "jira-scored"


def generate_test_case(root, files, issue):
    text = issue_text(issue)
    summary = (issue.get("fields") or {}).get("summary") or ""
    if "复现" in text or "步骤" in text:
        return f"测试用例：根据 Jira 描述的复现步骤验证「{summary}」，确认问题已修复。"
    if any(path.endswith(".proto.txt") for path in files):
        return f"测试用例：验证「{summary}」相关协议字段同步后，客户端与服务端请求响应兼容。"
    if any(path.endswith(".go") for path in files):
        return f"测试用例：验证「{summary}」相关服务端逻辑路径，确认接口处理结果符合预期。"
    if any(path.endswith(".lua") for path in files):
        return f"测试用例：验证「{summary}」相关客户端功能流程，确认界面表现和逻辑结果符合预期。"
    if "saga-exporter" in root:
        return f"测试用例：验证「{summary}」相关配置表导出流程，确认生成结果符合预期。"
    return f"测试用例：验证「{summary}」相关改动，确认问题已修复且核心流程符合预期。"


def branch_counts(root, branch):
    output = run(["git", "rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"], cwd=root).strip()
    left, right = output.split()
    return int(left), int(right)


def has_uncommitted(root, files):
    output = run(["git", "status", "--porcelain=v1", "--", *files], cwd=root)
    return bool(output.strip())


def sync_branch(root, branch, files, dry_run=False):
    current = run(["git", "branch", "--show-current"], cwd=root).strip()
    if current != branch:
        if run(["git", "status", "--porcelain=v1"], cwd=root).strip():
            raise SystemExit(f"Refusing to checkout {branch}: worktree is dirty on {current}")
        run(["git", "checkout", branch], cwd=root, dry_run=dry_run)

    run(["git", "fetch", "origin", branch], cwd=root, dry_run=dry_run)
    local_ahead, remote_ahead = branch_counts(root, branch) if not dry_run else (0, 0)
    if local_ahead == 0 and remote_ahead == 0:
        return

    stash_ref = None
    if files and has_uncommitted(root, files):
        msg = f"jira-submit-to-git-{os.getpid()}"
        run(["git", "stash", "push", "-m", msg, "--", *files], cwd=root, dry_run=dry_run)
        stash_ref = "stash@{0}"

    if local_ahead == 0:
        run(["git", "merge", "--ff-only", f"origin/{branch}"], cwd=root, dry_run=dry_run)
    else:
        run(["git", "rebase", f"origin/{branch}"], cwd=root, dry_run=dry_run)

    if stash_ref:
        run(["git", "stash", "pop", stash_ref], cwd=root, dry_run=dry_run)


def run_pre_commit_hooks(root, cfg, files, dry_run=False):
    hooks = cfg.get("pre_commit", [])
    if "make_pbproto_if_proto_changed" in hooks and any(path.startswith("proto/") for path in files):
        run(["make", "pbproto"], cwd=root, capture=False, dry_run=dry_run)


def commit_and_push(root, branch, files, commit_msg, dry_run=False):
    for path in files:
        run(["git", "add", "--", path], cwd=root, dry_run=dry_run)
    if not dry_run and not staged_files(root):
        raise SystemExit("No staged files after git add.")
    run(["git", "commit", "-m", commit_msg], cwd=root, dry_run=dry_run)
    run(["git", "push", "origin", branch], cwd=root, dry_run=dry_run)


def update_weekly(issue_key, dry_run=False):
    if not WEEKLY_SCRIPT.exists():
        print(f"weekly_report skipped: missing {WEEKLY_SCRIPT}", file=sys.stderr)
        return
    run([WEEKLY_SCRIPT, issue_key], dry_run=dry_run, capture=False)


def sync_proto_to_unity(root, cfg, files, dry_run=False):
    sync_cfg = cfg.get("sync_to_unity") or {}
    unity_repo = Path(sync_cfg.get("unity_repo", "/Users/songdc/ttdbl2_unity"))
    unity_proto_dir = sync_cfg.get("unity_proto_dir", "Assets/Config/ttdbl2_protobuf")
    proto_files = [path for path in files if path.endswith(".proto.txt")]
    if not proto_files:
        return
    for rel in proto_files:
        src = Path(root) / rel
        dest = unity_repo / unity_proto_dir / Path(rel).name
        print(f"+ sync proto to unity: {src} -> {dest}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def load_excel_table_config(path):
    with Path(path).open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Excel table config must be a list: {path}")
    return data


def table_display_name(item):
    return item.get("name") or item.get("rangeLocal") or item.get("range")


def normalize_filename(value):
    return Path(value).name if value else ""


def infer_excel_tables(root, cfg, files):
    export_cfg = cfg.get("excel_export") or {}
    tables_path = export_cfg.get("tables_config")
    if not tables_path:
        raise ValueError("excel_export.tables_config is not configured")

    tables = load_excel_table_config(tables_path)
    selected = []
    for rel in files:
        path = Path(rel)
        parts = path.parts
        basename = path.name
        matched = []
        for item in tables:
            if not item.get("enable", True):
                continue
            script_path = item.get("path")
            client_file = normalize_filename(item.get("clientFile"))
            server_file = normalize_filename(item.get("serverFile"))
            display_name = table_display_name(item)
            if not display_name:
                continue
            if len(parts) >= 3 and parts[0] == "tables" and parts[1] == script_path:
                matched.append(display_name)
            elif basename and basename in {client_file, server_file}:
                matched.append(display_name)
            elif display_name and display_name in rel:
                matched.append(display_name)
        selected.extend(matched)

    unique = []
    for name in selected:
        if name not in unique:
            unique.append(name)
    if not unique:
        raise ValueError("Could not infer Excel table names from submitted files")
    return unique


def trigger_excel_export(root, cfg, commit_msg, files, dry_run=False):
    export_cfg = cfg.get("excel_export") or {}
    if not export_cfg.get("enabled"):
        print("trigger_excel_export skipped: excel_export is disabled")
        return

    tables = infer_excel_tables(root, cfg, files)
    base_url = export_cfg.get("base_url", "").rstrip("/")
    app = export_cfg.get("app", "saga")
    branch = export_cfg.get("branch", "trunk-tw")
    author = export_cfg.get("author", "songdc")
    if not base_url:
        raise ValueError("excel_export.base_url is not configured")

    params = urllib.parse.urlencode({
        "app": app,
        "gitmsg": f"{commit_msg} --{author}",
        "branch": branch,
        "tables": ",".join(tables),
    })
    url = f"{base_url}/v1/api/export?{params}"
    print(f"+ trigger Excel export: branch={branch} tables={','.join(tables)}")
    if dry_run:
        print(f"+ {url}")
        return

    with urllib.request.urlopen(url, timeout=180) as resp:
        raw = resp.read().decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Excel export returned non-JSON response: {raw[:500]}") from exc
    if data.get("error") not in (0, None):
        raise RuntimeError(data.get("data") or raw)
    print(f"excel_export_result={data.get('data')}")


def after_push(root, cfg, issue_key, commit_msg, test_case, files, dry_run=False):
    hooks = cfg.get("after_push", [])
    errors = []
    for hook in hooks:
        try:
            if hook == "jira_test_comment":
                add_jira_comment(issue_key, test_case, dry_run=dry_run)
            elif hook == "weekly_report":
                update_weekly(issue_key, dry_run=dry_run)
            elif hook == "sync_to_unity":
                sync_proto_to_unity(root, cfg, files, dry_run=dry_run)
            elif hook == "trigger_excel_export":
                trigger_excel_export(root, cfg, commit_msg, files, dry_run=dry_run)
        except Exception as exc:
            errors.append(f"{hook}: {exc}")
    if errors:
        print("After-push hook failures:", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Submit Jira-related changes to Git linearly.")
    parser.add_argument("issue", help="Jira issue key or URL")
    parser.add_argument("--repo", default=".", help="Repository path. Defaults to current directory.")
    parser.add_argument("--branch", help="Override configured target branch.")
    parser.add_argument("--file", action="append", dest="files", help="Explicit file to submit. May be repeated.")
    parser.add_argument("--test-case", help="Explicit Jira test-case comment text, with or without the 测试用例： prefix.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing Git/Jira/Confluence.")
    parser.add_argument("--list-files", action="store_true", help="Infer files and test-case comment, then exit before Git sync.")
    parser.add_argument("--no-after-push", action="store_true", help="Skip Jira comment, weekly report, and repo-specific hooks.")
    args = parser.parse_args()

    issue_key = normalize_issue_key(args.issue)
    issue = read_issue(issue_key)
    summary = (issue.get("fields") or {}).get("summary")
    if not summary:
        raise SystemExit(f"Jira issue {issue_key} has no summary in response")
    commit_msg = f"{issue_key}{summary}"

    root = repo_root(args.repo)
    configs = load_config()
    cfg = repo_config(root, configs)
    branch = args.branch or cfg["branch"]

    if args.files:
        files = args.files
        excluded = []
        source = "explicit"
    else:
        files, excluded, source = infer_files(root, cfg, issue)

    test_case = args.test_case or generate_test_case(root, files, issue)
    if not test_case.startswith("测试用例："):
        test_case = f"测试用例：{test_case}"

    print(json.dumps({
        "issue": issue_key,
        "repo": root,
        "branch": branch,
        "commit_message": commit_msg,
        "file_source": source,
        "files": files,
        "excluded_dirty_files": excluded[:80],
        "test_case_comment": test_case,
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))

    if args.list_files:
        return

    sync_branch(root, branch, files, dry_run=args.dry_run)
    run_pre_commit_hooks(root, cfg, files, dry_run=args.dry_run)
    commit_and_push(root, branch, files, commit_msg, dry_run=args.dry_run)
    if not args.no_after_push:
        after_push(root, cfg, issue_key, commit_msg, test_case, files, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
