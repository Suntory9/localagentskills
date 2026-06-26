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
import uuid


BASE_URL = "https://xindong.atlassian.net"
SPACE_KEY = "RE"
DEFAULT_ACCOUNT_ID = "628bb637f2ee4a0069dee6bc"
JIRA_SERVER_ID = "55efe888-7a9b-3d20-b659-59c3da70cb51"
JIRA_SERVER_NAME = "System Jira"


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


def auth_header():
    load_shell_env()
    email = os.environ.get("ATLASSIAN_EMAIL")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if not email or not token:
        raise SystemExit("Missing ATLASSIAN_EMAIL or ATLASSIAN_API_TOKEN after loading ~/.zshrc")
    encoded = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def confluence_request(method, path, data=None):
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE_URL + "/wiki" + path, data=body, method=method, headers=auth_header())
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Confluence HTTP {exc.code}: {detail}") from exc


def normalize_issue_key(value):
    match = re.search(r"[A-Z][A-Z0-9]+-\d+", value)
    if not match:
        raise SystemExit(f"Could not find Jira issue key in: {value}")
    return match.group(0)


def parse_date(value):
    if value:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    return dt.date.today()


def week_range(day):
    start = day - dt.timedelta(days=day.weekday())
    end = start + dt.timedelta(days=4)
    return start, end


def format_m_d(day):
    return f"{day.month}.{day.day}"


def weekly_title(day):
    start, end = week_range(day)
    return f"程序周报{start.year}.{format_m_d(start)}-{format_m_d(end)}"


def find_weekly_page(day, page_id=None):
    if page_id:
        return get_page(page_id)
    env_page_id = os.environ.get("JIRA_WEEKLY_REPORT_PAGE_ID")
    if env_page_id:
        return get_page(env_page_id)

    title = weekly_title(day)
    cql = f'space = "{SPACE_KEY}" AND type = page AND title = "{title}"'
    data = confluence_request("GET", f"/rest/api/content/search?cql={urllib.parse.quote(cql)}&limit=2")
    results = data.get("results") or []
    if not results:
        raise SystemExit(f"Could not find Confluence weekly report page titled: {title}")
    if len(results) > 1:
        ids = ", ".join(item.get("id", "") for item in results)
        raise SystemExit(f"Multiple weekly report pages found for {title}: {ids}")
    return get_page(results[0]["id"])


def get_page(page_id):
    return confluence_request(
        "GET",
        f"/rest/api/content/{page_id}?expand=body.storage,version,title,space",
    )


def update_page(page, new_body, message):
    payload = {
        "id": page["id"],
        "type": page.get("type", "page"),
        "title": page["title"],
        "version": {
            "number": int(page["version"]["number"]) + 1,
            "message": message,
        },
        "body": {
            "storage": {
                "value": new_body,
                "representation": "storage",
            },
        },
    }
    return confluence_request("PUT", f"/rest/api/content/{page['id']}", payload)


def strip_tags(value):
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", "", value)


def find_tag_spans(html, tag_name):
    pattern = re.compile(rf"<{tag_name}\b[^>]*>.*?</{tag_name}>", re.S)
    return list(pattern.finditer(html))


def find_cell_spans(row_html):
    pattern = re.compile(r"<t[dh]\b[^>]*>.*?</t[dh]>", re.S)
    return list(pattern.finditer(row_html))


def date_column(header_row, day):
    target = format_m_d(day)
    cells = find_cell_spans(header_row)
    for index, cell in enumerate(cells):
        if strip_tags(cell.group(0)) == target:
            return index
    header = " | ".join(strip_tags(cell.group(0)) for cell in cells)
    raise SystemExit(f"Could not find date column {target}; header cells: {header}")


def row_for_account(rows, account_id):
    needle = f'ri:account-id="{account_id}"'
    for row in rows:
        if needle in row.group(0):
            return row
    raise SystemExit(f"Could not find weekly report row for account id: {account_id}")


def jira_macro(issue_key):
    return (
        f'<p><ac:structured-macro ac:name="jira" ac:schema-version="1" '
        f'ac:macro-id="{uuid.uuid4()}">'
        f'<ac:parameter ac:name="key">{issue_key}</ac:parameter>'
        f'<ac:parameter ac:name="serverId">{JIRA_SERVER_ID}</ac:parameter>'
        f'<ac:parameter ac:name="server">{JIRA_SERVER_NAME}</ac:parameter>'
        f"</ac:structured-macro></p>"
    )


def replace_cell_inner(cell_html, new_inner):
    open_match = re.match(r"(<t[dh]\b[^>]*>)(.*)(</t[dh]>)", cell_html, re.S)
    if not open_match:
        raise SystemExit("Could not parse target table cell.")
    return f"{open_match.group(1)}{new_inner}{open_match.group(3)}"


def is_effectively_empty(cell_html):
    inner = re.sub(r"^<t[dh]\b[^>]*>|</t[dh]>$", "", cell_html, flags=re.S)
    compact = re.sub(r"\s+", "", inner)
    return compact in ("", "<p/>") or compact.startswith("<p") and compact.endswith("/>")


def append_issue_to_cell(cell_html, issue_key):
    if f">{issue_key}<" in cell_html or f">{issue_key}</ac:parameter>" in cell_html:
        return cell_html, False
    macro = jira_macro(issue_key)
    if is_effectively_empty(cell_html):
        return replace_cell_inner(cell_html, macro), True
    return replace_cell_inner(cell_html, re.sub(r"^<t[dh]\b[^>]*>|</t[dh]>$", "", cell_html, flags=re.S) + macro), True


def update_body(body, day, account_id, issue_key):
    rows = find_tag_spans(body, "tr")
    if not rows:
        raise SystemExit("Could not find any table rows in weekly report page.")
    col = date_column(rows[0].group(0), day)
    target_row = row_for_account(rows, account_id)
    row_html = target_row.group(0)
    cells = find_cell_spans(row_html)
    if col >= len(cells):
        raise SystemExit(f"Target row has only {len(cells)} cells; date column index is {col}.")
    cell = cells[col]
    new_cell, changed = append_issue_to_cell(cell.group(0), issue_key)
    if not changed:
        return body, False
    new_row = row_html[: cell.start()] + new_cell + row_html[cell.end() :]
    return body[: target_row.start()] + new_row + body[target_row.end() :], True


def main():
    parser = argparse.ArgumentParser(description="Add a Jira issue to the current programming weekly report.")
    parser.add_argument("issue", help="Jira issue key or URL")
    parser.add_argument("--date", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--account-id", default=os.environ.get("JIRA_WEEKLY_ACCOUNT_ID", DEFAULT_ACCOUNT_ID))
    parser.add_argument("--page-id", help="Confluence page id. Defaults to current week title lookup.")
    parser.add_argument("--dry-run", action="store_true", help="Check and print the target without updating Confluence.")
    args = parser.parse_args()

    issue_key = normalize_issue_key(args.issue)
    day = parse_date(args.date)
    page = find_weekly_page(day, args.page_id)
    body = page["body"]["storage"]["value"]
    new_body, changed = update_body(body, day, args.account_id, issue_key)
    target = f"{page['title']}#{format_m_d(day)}"
    if not changed:
        print(f"weekly_report skipped: {issue_key} already exists in {target}")
        return
    if args.dry_run:
        print(f"weekly_report dry-run: would add {issue_key} to {target}")
        return
    update_page(page, new_body, f"Add {issue_key} to weekly report")
    print(f"weekly_report updated: added {issue_key} to {target}")


if __name__ == "__main__":
    main()
