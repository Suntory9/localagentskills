---
name: jira-submit-to-git
description: >-
  Submit Jira-related local changes from one of the configured XD repositories
  directly to the repository's configured trunk/default branch. Use when the
  user gives a Jira key or URL, or says phrases such as "合并到主干",
  "提交到主干", "更新到主干", "提主干", "submit to main/trunk", or "push to
  main/trunk" for existing local changes. Infer the Jira key from the current
  conversation when the user omits it and a single recent key is unambiguous.
  Read Jira, infer the changed file set and test-case comment from Jira plus
  local diff, create a linear commit titled <JIRA_KEY><summary>, push it, then
  update follow-up systems such as Jira comments, programming weekly report,
  Unity proto sync, or table export hooks. Supported repos:
  /Users/songdc/ttdbl2_unity, /Users/songdc/ttdbl2_protobuf, /Users/songdc/zserver,
  /Users/songdc/saga-exporter.
---

# Jira Submit To Git

## Purpose

Use this skill for fast Jira-driven submission of existing local changes. The
user is expected to have reviewed the code before asking. Do not perform a
code-review pass unless the user explicitly asks for one.

Also use this skill when the user says "合并到主干", "提交到主干",
"更新到主干", "提主干", "submit to main/trunk", or "push to main/trunk" in a
supported repository. In this skill, "主干/main/trunk" means the configured
default branch for the current repository, not necessarily a literal branch
named `main`.

This skill is intentionally separate from `jira-unity-to-main`; do not edit or
depend on that skill's workflow except for reusing the weekly-report script.

## Default Behavior

1. Normalize the Jira input to a key such as `TTDBL-42389`.
   - If the user omits a key but the current conversation contains exactly one
     recent Jira key or URL, use that key.
   - If multiple Jira keys are plausible, ask which one to submit before
     running the script.
   - Do not ask when the latest user message clearly continues the immediately
     preceding Jira task.
2. Read Jira through the Jira connector when available. Include fields:
   `summary`, `description`, `comment`, and `attachment`.
3. If image attachments are relevant to understanding the issue, download and
   inspect them before inferring files or test cases.
4. Detect the current repository with `git rev-parse --show-toplevel`, then load
   `config/repos.json`.
5. Resolve "主干/main/trunk" to the configured default branch for that repository:
   - `/Users/songdc/ttdbl2_unity`: `2023-11-28-Unity2021-3-13`
   - `/Users/songdc/ttdbl2_protobuf`: `develop`
   - `/Users/songdc/zserver`: `develop`
   - `/Users/songdc/saga-exporter`: `master`
   If the user explicitly names a branch, pass it with `--branch`.
6. Infer the submit file set automatically:
   - Already staged files are treated as user-confirmed and may be submitted.
   - Otherwise inspect dirty files, Jira text, and local diffs.
   - For `ttdbl2_unity`, ignore unstaged dirty files under:
     `Assets/Art/`, `Assets/Models/`, `Assets/TextMesh Pro/`,
     `Assets/Scripts/LuaScript/Data/ConfigTableCN/`,
     `Assets/Scripts/LuaScript/Data/ConfigTableGL/`.
   - Exclude temporary markdown notes, logs, and IDE files unless explicitly
     staged or requested.
   - If confidence is low, stop and ask the user instead of committing.
7. Generate a Jira comment test-case line automatically:
   `测试用例：...`
   Prefer Jira reproduction or acceptance text. Otherwise infer a conservative
   test case from changed file types and modules.
8. Submit linearly:
   - `git fetch origin <branch>`
   - Rebase local commits when needed; never create a merge commit.
   - If unstaged selected files need branch sync, stash only selected files,
     sync/rebase, then pop the stash.
   - Commit with exact title `<JIRA_KEY><summary>`.
   - Push to `origin <branch>`.
9. After push succeeds:
   - Add the generated Jira comment only after checking existing Jira comments.
     If a similar visible `测试用例：...` comment already exists, skip writing a
     duplicate and report that it was skipped.
   - Update the programming weekly report using
     `/Users/songdc/.codex/skills/jira-unity-to-main/scripts/update_weekly_report.py`.
   - For `ttdbl2_protobuf`, sync changed proto files into
     `/Users/songdc/ttdbl2_unity/Assets/Config/ttdbl2_protobuf/` and tell the
     user Unity still needs its own submit step.
   - For `saga-exporter`, trigger the web Excel export API after push. Use
     `trunk-tw`, title `<JIRA_KEY><summary> --songdc`, and infer the selected
     table names from `tables/tables.json` plus the submitted files. If table
     inference fails, report the hook failure instead of guessing.

## Recommended Command

Run from inside the target repository:

```bash
zsh -lc '/Users/songdc/.codex/skills/jira-submit-to-git/scripts/submit_jira_to_git.py TTDBL-42389 --dry-run'
```

If the dry run selects the expected files and comment, run without `--dry-run`:

```bash
zsh -lc '/Users/songdc/.codex/skills/jira-submit-to-git/scripts/submit_jira_to_git.py TTDBL-42389'
```

## Guardrails

- Never use `git add .` in `ttdbl2_unity`.
- Never use a merge pull. Prefer `fetch`, `rebase`, and fast-forward sync.
- Never push when file inference reports low confidence.
- Never include ignored Unity dirty paths unless they are already staged or the
  user explicitly names them.
- Never update Jira comments or weekly report before code push succeeds.
- Never add a duplicate Jira test-case comment; read existing comments first and
  skip when a similar `测试用例：...` comment already exists.
- Never guess the Jira summary. Read it from Jira.
- Do not silently skip failed after-push hooks; report them separately from the
  successful Git push.

## Scripts

- `scripts/submit_jira_to_git.py`: deterministic submit helper with dry-run,
  file inference, linear Git sync, Jira comment, weekly-report hook, and
  protobuf-to-Unity sync hook.
- `config/repos.json`: repository branch defaults and per-repo hook settings.
