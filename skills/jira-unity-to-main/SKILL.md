---
name: jira-unity-to-main
description: >-
  Read a Jira issue, extract its summary, review and validate existing local
  Unity changes, then submit those changes directly onto the target trunk
  branch. Use when Codex is given a Jira URL or key such as TTDBL-42389 and
  should (1) read the issue through Atlassian credentials, (2) generate the
  commit title from the Jira summary, (3) fetch and pull the target branch, and
  (4) review, validate, commit, and push existing changes with the Jira title as
  the commit message. Default target branch:
  2023-11-28-Unity2021-3-13.
---

# Jira Unity To Main

## Overview

Use this skill when the user already has Unity client changes and wants a Jira-driven submission workflow: read the Jira issue, derive the standardized commit message, sync the target branch, review and validate the current changes, then submit the result to the trunk branch.

Prefer to read the Jira issue through [$atlassian-rovo](app://connector_692de805e3ec8191834719067174a384) first, then continue the submission workflow in this skill.

Prefer this skill when the user gives a Jira URL instead of describing the bug in detail.

## Workflow

1. Normalize the issue input.
   Accept either a full Jira URL like `https://xindong.atlassian.net/browse/TTDBL-42389` or a plain key like `TTDBL-42389`.

2. Load Jira credentials before reading the issue.
   Run `source ~/.zshrc >/dev/null 2>&1` in `zsh` before invoking Jira commands so `ATLASSIAN_EMAIL` and `ATLASSIAN_API_TOKEN` are available in new Codex threads.

3. Read the Jira issue.
   Prefer [$atlassian-rovo](app://connector_692de805e3ec8191834719067174a384) for the read-only Jira fetch step so the summary is available.
   If the connector path is unavailable or incomplete, use `scripts/read_issue.sh <jira-url-or-key>` as a fallback.
   If the read fails, inspect whether credentials are present and whether the current account has permission to view the issue.

4. Extract the commit title from Jira.
   Use the exact format:
   `<JIRA_KEY><summary>`

   Example:
   `TTDBL-42389【图鉴优化】图鉴排名刷新问题`

5. Confirm the target branch.
   Default to `2023-11-28-Unity2021-3-13`.
   If the user explicitly provides another branch, use that branch instead.

6. Sync the target branch before the final commit sequence.
   Use non-interactive git commands.
   Preferred sequence:

```bash
git checkout 2023-11-28-Unity2021-3-13
git fetch origin
git pull origin 2023-11-28-Unity2021-3-13
```

7. Review the existing local changes.
   Inspect the changed files and confirm they are relevant to the Jira issue.
   Do not implement new Unity client functionality as part of this skill.
   Do not revert unrelated local changes.

8. Validate as appropriate and perform a code review pass.
   Run targeted checks when feasible.
   Check the final diff for obvious correctness issues, unrelated edits, generated-file mistakes, and missing companion files.
   If validation cannot be run, say so clearly.

9. Commit and push after the existing changes pass review and validation.
   Use the Jira-derived title as the full commit message.
   Prefer `scripts/submit_issue_fix.sh <jira-url-or-key> <repo-path> [branch] [file ...]`.
   Pass explicit changed files whenever possible.
   If no files are passed, the script uses already staged changes and refuses to proceed when nothing is staged.
   Exclude newly created requirement or task markdown files by default, such as ticket notes, dev plans, or ad hoc `*.md` documents, unless the user explicitly asks to submit them to trunk.

   Preferred sequence:

```bash
git add <changed-files>
git commit -m "TTDBL-42389【图鉴优化】图鉴排名刷新问题"
git push origin 2023-11-28-Unity2021-3-13
```

10. After a successful push, add the Jira link to the programming weekly report.
   Prefer `scripts/update_weekly_report.py <jira-url-or-key>` after the push has completed.
   The script locates the current workday's `程序周报...` Confluence page in the `RE` space, finds the `songdiancan` row and today's `M.D` column, and appends the Jira issue as an inline card.
   Run this step only after the branch push succeeds.
   If the weekly report page, date column, or `songdiancan` row cannot be found, do not treat the source-code submission as failed; report the weekly-report update failure clearly.
   If the Jira link is already present, leave the page unchanged.

## Guardrails

- Never assume Jira credentials are already present in the current thread; load `~/.zshrc` first.
- Prefer `[$atlassian-rovo](app://connector_692de805e3ec8191834719067174a384)` for Jira content retrieval instead of generic webpage fetching.
- Never invent the Jira summary; read it from Jira and use it verbatim in the commit title.
- Never implement new Unity client functionality as part of this skill.
- Never use interactive git flows.
- Never revert unrelated worktree changes.
- Never auto-stage the full repo when the changed file set is known; prefer explicit files.
- Never submit newly created requirement, task, or temporary markdown documents to trunk by default. Files such as `TTDBL-xxxx*.md`, dev notes, or one-off dev plans should stay out of the commit unless the user explicitly asks to include them.
- If the worktree contains unrelated edits that conflict with the Jira submission, pause and ask the user before proceeding.
- If push requires approval or elevated permissions, request it explicitly.
- Never update the programming weekly report before the code push succeeds.
- When updating the weekly report, modify only the current date cell in the `songdiancan` row and avoid rewriting unrelated page content.
- If Confluence reports a version conflict or the page changed during update, re-read the page once and retry only if the target cell can still be identified unambiguously.

## Quick Commands

Read issue:

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; /Users/songdc/.codex/skills/jira-unity-to-main/scripts/read_issue.sh https://xindong.atlassian.net/browse/TTDBL-42389'
```

Or invoke:

```text
Use [$atlassian-rovo](app://connector_692de805e3ec8191834719067174a384) to read TTDBL-42389, then continue with $jira-unity-to-main.
```

Submit existing changes:

```bash
zsh -lc '/Users/songdc/.codex/skills/jira-unity-to-main/scripts/submit_issue_fix.sh TTDBL-42389 /Users/songdc/ttdbl2_unity 2023-11-28-Unity2021-3-13 Assets/Scripts/LuaScript/Views/Collection/CollectionView.lua'
```

Update weekly report after a successful push:

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; /Users/songdc/.codex/skills/jira-unity-to-main/scripts/update_weekly_report.py TTDBL-42389'
```

Extract the commit title from the returned JSON:

- Jira key: `.key`
- Summary: `.fields.summary`
- Commit title: `.key + .fields.summary`

## scripts/

- `scripts/read_issue.sh`: Read a Jira issue with Atlassian credentials from `~/.zshrc`.
- `scripts/submit_issue_fix.sh`: Fetch, pull, commit, and push existing changes using the Jira title as the commit message.
- `scripts/update_weekly_report.py`: Add the Jira link to the current workday cell in the `songdiancan` row of the programming weekly report.
