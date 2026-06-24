#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = "https://xindong.atlassian.net"
WIKI_BASE = BASE_URL + "/wiki"
SPACE_KEY = "RE"
REPORT_TITLE_PREFIX = "程序周报"
REPORT_ROOT_PAGE_ID = "243675239"
DEFAULT_ACCOUNT_ID = "628bb637f2ee4a0069dee6bc"  # songdiancan


def load_shell_env():
    cmd = "source ~/.zshrc >/dev/null 2>&1 || true; env"
    result = subprocess.run(["zsh", "-lc", cmd], check=False, text=True, stdout=subprocess.PIPE)
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def normalize_issue_url(issue_input):
    match = re.search(r"TTDBL-\d+", issue_input)
    if not match:
        raise SystemExit(f"Could not find Jira issue key in: {issue_input}")
    key = match.group(0)
    return key, f"{BASE_URL}/browse/{key}"


def request(method, path, auth, data=None):
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(WIKI_BASE + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def request_url(method, url, auth, data=None):
    if url.startswith("/wiki/"):
        path = url[len("/wiki") :]
    elif url.startswith("https://"):
        path = url.removeprefix(WIKI_BASE)
    else:
        path = url
    return request(method, path, auth, data)


def parse_date(value):
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def parse_title_range(title, default_year):
    # Supports titles like:
    # 程序周报2026.5.6-2026.5.9
    # 程序周报2026.7.12-7.16
    match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})-(?:(\d{4})\.)?(?:(\d{1,2})\.)?(\d{1,2})", title)
    if not match:
        return None
    start_year, start_month, start_day, end_year, end_month, end_day = match.groups()
    sy = int(start_year)
    sm = int(start_month)
    sd = int(start_day)
    ey = int(end_year) if end_year else sy
    em = int(end_month) if end_month else sm
    ed = int(end_day)
    try:
        return dt.date(sy, sm, sd), dt.date(ey, em, ed)
    except ValueError:
        return None


def search_report_page(auth, target_date):
    query_text = f"{REPORT_TITLE_PREFIX}{target_date.year}.{target_date.month}"
    cql = f'space = "{SPACE_KEY}" AND title ~ "{query_text}" AND type = page'
    params = urllib.parse.urlencode({"cql": cql, "limit": 50})
    data = request("GET", f"/rest/api/content/search?{params}", auth)
    candidates = data.get("results", [])
    for page in candidates:
        date_range = parse_title_range(page.get("title", ""), target_date.year)
        if not date_range:
            continue
        start, end = date_range
        if start <= target_date <= end:
            return page["id"], page["title"]

    next_path = (
        f"/api/v2/pages/{REPORT_ROOT_PAGE_ID}/descendants?"
        + urllib.parse.urlencode({"depth": 4, "limit": 250})
    )
    while next_path:
        data = request_url("GET", next_path, auth)
        for page in data.get("results", []):
            if page.get("type") != "page":
                continue
            date_range = parse_title_range(page.get("title", ""), target_date.year)
            if not date_range:
                continue
            start, end = date_range
            if start <= target_date <= end:
                return page["id"], page["title"]
        next_path = (data.get("_links") or {}).get("next")
    raise SystemExit(f"Could not find {REPORT_TITLE_PREFIX} page containing {target_date.isoformat()}")


def node_text(node):
    parts = []

    def walk(value):
        if isinstance(value, dict):
            if value.get("type") == "text":
                parts.append(value.get("text", ""))
            attrs = value.get("attrs") or {}
            if "text" in attrs:
                parts.append(attrs["text"])
            for child in value.get("content") or []:
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return "".join(parts)


def node_has_url(node, url):
    found = False

    def walk(value):
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            if (value.get("attrs") or {}).get("url") == url:
                found = True
                return
            for child in value.get("content") or []:
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


def cell_has_account(cell, account_id):
    found = False

    def walk(value):
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            attrs = value.get("attrs") or {}
            if value.get("type") == "mention" and attrs.get("id") == account_id:
                found = True
                return
            for child in value.get("content") or []:
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(cell)
    return found


def jira_paragraph(issue_url):
    return {
        "type": "paragraph",
        "content": [
            {"type": "inlineCard", "attrs": {"url": issue_url}},
            {"type": "text", "text": " "},
        ],
    }


def update_adf(adf, issue_url, target_date, account_id):
    target_day = f"{target_date.month}.{target_date.day}"
    table = next((node for node in adf.get("content", []) if node.get("type") == "table"), None)
    if table is None:
        raise SystemExit("Could not find weekly report table")
    rows = table.get("content") or []
    if not rows:
        raise SystemExit("Weekly report table is empty")

    header_cells = rows[0].get("content") or []
    col_idx = None
    for index, cell in enumerate(header_cells):
        if node_text(cell).strip() == target_day:
            col_idx = index
            break
    if col_idx is None:
        raise SystemExit(f"Could not find date column: {target_day}")

    target_row = None
    for row in rows:
        cells = row.get("content") or []
        if cells and cell_has_account(cells[0], account_id):
            target_row = row
            break
    if target_row is None:
        raise SystemExit(f"Could not find account row: {account_id}")

    cells = target_row.get("content") or []
    if col_idx >= len(cells):
        raise SystemExit("Target row does not contain the date column")
    cell = cells[col_idx]
    if node_has_url(cell, issue_url):
        return False

    content = cell.setdefault("content", [])
    if len(content) == 1 and content[0].get("type") == "paragraph" and not content[0].get("content"):
        content[0] = jira_paragraph(issue_url)
    else:
        content.append(jira_paragraph(issue_url))
    return True


def main():
    parser = argparse.ArgumentParser(description="Add a Jira link to the current programming weekly report.")
    parser.add_argument("issue", help="Jira issue key or URL, e.g. TTDBL-42389")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID, help="Confluence account id for the target row.")
    parser.add_argument("--dry-run", action="store_true", help="Locate and modify in memory, but do not update Confluence.")
    args = parser.parse_args()

    load_shell_env()
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        raise SystemExit("Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc")

    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    issue_key, issue_url = normalize_issue_url(args.issue)
    target_date = parse_date(args.date) if args.date else dt.date.today()

    page_id, _ = search_report_page(auth, target_date)
    page = request("GET", f"/api/v2/pages/{page_id}?body-format=atlas_doc_format", auth)
    title = page["title"]
    version = page["version"]["number"]
    adf = json.loads(page["body"]["atlas_doc_format"]["value"])

    changed = update_adf(adf, issue_url, target_date, args.account_id)
    if not changed:
        print(f"weekly_report=already_present issue={issue_key} page_id={page_id} title={title}")
        return
    if args.dry_run:
        print(f"weekly_report=dry_run_changed issue={issue_key} page_id={page_id} title={title}")
        return

    payload = {
        "id": page_id,
        "status": "current",
        "title": title,
        "body": {"representation": "atlas_doc_format", "value": json.dumps(adf, ensure_ascii=False)},
        "version": {"number": version + 1, "message": f"Add {issue_key} to songdiancan daily report"},
    }
    request("PUT", f"/api/v2/pages/{page_id}", auth, payload)
    print(f"weekly_report=updated issue={issue_key} page_id={page_id} title={title} version={version + 1}")


if __name__ == "__main__":
    main()
