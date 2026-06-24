---
name: jira-unity-to-tw
description: Move Jira-related Unity commits onto the TW branch in this project, with commit lookup, dependency analysis, remote sync checks, cherry-pick execution, conflict handling, validation, required linear push, and Jira status transition after a successful TW push. Use when the user wants to port a TTDBL fix or Unity commit to the TW branch. If the user says “台服分支” without naming a branch, default to `archive/branch/tw/tw-obt-design-2024-1-25`. Prefer the existing TW worktree at `/Users/songdc/ttdbl2_unity_tw`; only fall back to a temporary worktree if that worktree is missing or on the wrong branch.
---

# Jira Unity To Tw

Use this skill to move one or more Unity commits, usually identified by Jira key or Jira title, onto the TW branch safely.

After a successful linear push to the TW branch, this skill should also advance the Jira issue to the appropriate testing state when the workflow allows it. Default target status: `开发服测试中`; acceptable fallback target status: `待验收` when `开发服测试中` is not reachable from the current Jira workflow.

## Defaults

- Default TW branch: `archive/branch/tw/tw-obt-design-2024-1-25`
- Default TW worktree: `/Users/songdc/ttdbl2_unity_tw`
- If the user says “台服分支”, treat it as the default TW branch unless they explicitly override it.

## TW worktree policy

Treat `/Users/songdc/ttdbl2_unity_tw` as a dedicated TW integration worktree.
It is not for normal feature development or temporary local edits.

Default handling:
- always prefer the existing TW worktree
- if it is behind remote, sync it first
- if it contains local uncommitted changes, discard them and restore the worktree to branch HEAD before continuing
- only create a temporary worktree when the existing TW worktree is missing or on the wrong branch

Use these commands when the TW worktree is dirty:

```bash
git -C /Users/songdc/ttdbl2_unity_tw reset --hard HEAD
git -C /Users/songdc/ttdbl2_unity_tw clean -fd
```

Then sync it:

```bash
git -C /Users/songdc/ttdbl2_unity_tw fetch origin
git -C /Users/songdc/ttdbl2_unity_tw pull --ff-only origin archive/branch/tw/tw-obt-design-2024-1-25
```

## Workflow

1. Identify the commit set.
   Accept a Jira key, Jira URL, commit SHA, commit range, or title keyword.
   If the user provides only a Jira key or title, locate the matching commit first.

2. Inspect repository state.
   Check:
   - source branch and requested commit set
   - whether the target already contains the change
   - whether the commit is a merge commit
   - whether the source commit looks self-contained

   Preferred commands:

```bash
git status --short
git branch --show-current
git branch --all --list
git branch --contains <sha>
git show --stat <sha>
git log --oneline --decorate --all --grep='<keyword>'
```

3. Analyze portability.
   Inspect changed files, nearby commits, generated assets, config dependencies, and target-branch compatibility.

4. Prepare the TW worktree.
   Use `/Users/songdc/ttdbl2_unity_tw` by default.
   Check its branch first.
   If the branch is correct but the worktree is dirty, discard local changes because this worktree is reserved for TW porting operations.
   If it is behind remote, fetch and fast-forward before continuing.

5. Apply the port.
   Prefer `git cherry-pick <sha>` for isolated fixes.
   Use ordered cherry-picks for small dependency chains.
   Use manual porting only when branch divergence makes cherry-pick misleading.

6. Handle conflicts carefully.
   Do not guess silently.
   Inspect conflicted files, explain tradeoffs, and only then resolve.

7. Validate the result.
   Run the smallest useful check for the changed area.
   At minimum, inspect the diff/stat to confirm the intended change arrived.

8. Push linearly after validation.
   Pushing to the TW branch is part of this workflow, not optional.
   Before pushing, re-check the remote branch. If the remote advanced after the local cherry-pick, rebase the local cherry-pick onto `origin/archive/branch/tw/tw-obt-design-2024-1-25`, re-run validation, then push.
   Never use `git merge`, never create a merge commit, and never use a non-fast-forward push.

9. Transition the Jira issue after a successful TW push.
   If the TW push succeeds and the task is tied to a Jira issue, query the issue's available transitions and move it forward.
   Default desired status: `开发服测试中`.
   Acceptable fallback status: `待验收`.
   Practical expectation: issues often start in states such as `处理中` or `待合并`, then move to `开发服测试中` after the TW push lands.
   Some workflows expose `处理中 -> 待验收` instead of a direct or unambiguous path to `开发服测试中`; in that case, transition to `待验收` and still add the Unity test case comment.
   Before transitioning, prepare a concise Unity test case comment that describes how QA can reproduce or verify the issue in the Unity client.
   The Jira comment must use this exact visible format: `测试用例：XXXX`.
   If the user did not provide a test case explicitly, derive one from the Jira description, screenshots, fix diff, and expected Unity interaction path.
   Use `scripts/transition_issue.sh <jira-url-or-key> '开发服测试中' '测试用例：XXXX'`.
   If `开发服测试中` is unavailable but `待验收` is available, use `scripts/transition_issue.sh <jira-url-or-key> '待验收' '测试用例：XXXX'`.
   If `开发服测试中` is not an immediate transition from the current state, the script may auto-advance through intermediate statuses only when each step is unambiguous.
   Example: if Jira only offers `处理中 -> 已处理 -> 开发服测试中`, the script may move through both steps automatically.
   When Jira exposes a transition screen with a “处理措施” style field, prefer filling it with `BUG 已修复` for bug-fix transitions.
   When the final target status is reached, the script also posts the test case comment if one was provided.
   Before posting, it must read existing Jira comments; if a similar visible `测试用例：...` comment already exists, skip writing a duplicate and report that it was skipped.
   If the path branches and neither `开发服测试中` nor `待验收` is safely available, list the available transitions and report that clearly instead of guessing.

## Safety rules

- Do not auto-process merge commits without explicit confirmation.
- Do not assume a requested commit is self-contained.
- Do not use destructive reset commands outside the dedicated TW worktree unless explicitly requested.
- In the dedicated TW worktree, if local changes exist, discard them before syncing and cherry-picking.
- Prefer `git pull --ff-only` when syncing the TW branch.
- Never use `git merge` or create a merge commit in the TW worktree.
- If the TW remote advances after cherry-pick, use `git rebase origin/archive/branch/tw/tw-obt-design-2024-1-25`, then validate again before pushing.
- Never stop after local validation when the cherry-pick succeeded; push the TW branch unless a safety rule blocks the push.
- If the target already contains the change, stop and report that.
- If the existing TW worktree is usable, prefer it over creating a temporary worktree.
- Never mark Jira as advanced unless the TW push actually succeeded.
- Never guess the transition id. Resolve it from Jira's current available transitions each time.
- If the desired Jira status is unavailable, check whether the fallback status `待验收` is available before reporting failure.
- Never stop after a successful fallback transition without adding the test case comment.
- Never add a duplicate Jira test-case comment; read existing comments first and
  skip when a similar `测试用例：...` comment already exists.
- Only auto-advance through intermediate Jira statuses when there is exactly one available transition at each step.

## Preferred command sequence

```bash
git -C /Users/songdc/ttdbl2_unity_tw status --short
git -C /Users/songdc/ttdbl2_unity_tw branch --show-current
git -C /Users/songdc/ttdbl2_unity_tw reset --hard HEAD
git -C /Users/songdc/ttdbl2_unity_tw clean -fd
git -C /Users/songdc/ttdbl2_unity_tw fetch origin
git -C /Users/songdc/ttdbl2_unity_tw pull --ff-only origin archive/branch/tw/tw-obt-design-2024-1-25
git -C /Users/songdc/ttdbl2_unity_tw cherry-pick <sha>
git -C /Users/songdc/ttdbl2_unity_tw fetch origin
git -C /Users/songdc/ttdbl2_unity_tw rebase origin/archive/branch/tw/tw-obt-design-2024-1-25
git -C /Users/songdc/ttdbl2_unity_tw push origin archive/branch/tw/tw-obt-design-2024-1-25
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; /Users/songdc/.codex/skills/jira-unity-to-tw/scripts/transition_issue.sh TTDBL-42572 "开发服测试中" "测试用例：在 Unity 中进入对应功能界面，按 Jira 描述复现操作路径，确认修复后的表现符合预期。"'
```

Fallback Jira transition when the workflow only exposes `待验收`:

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; /Users/songdc/.codex/skills/jira-unity-to-tw/scripts/transition_issue.sh TTDBL-42572 "待验收" "测试用例：在 Unity 中进入对应功能界面，按 Jira 描述复现操作路径，确认修复后的表现符合预期。"'
```

## Escalate before proceeding when

- the commit is a merge commit
- the target already partly contains the change
- the commit depends on multiple earlier commits
- the request might require manual porting instead of cherry-pick
- a linear push is blocked by conflicts, remote divergence, or branch protection
- the Jira workflow offers neither `开发服测试中` nor the fallback `待验收` after the TW push

## Output requirements

For analysis:
- recommended commit set
- cherry-pick safety assessment
- dependency or divergence risks
- recommended command sequence

For execution:
- target branch used
- whether the existing TW worktree was reused
- whether local TW worktree changes were discarded
- whether remote sync was checked
- whether a pull was needed
- exact commits applied
- whether conflicts occurred
- whether the TW branch was pushed
- whether Jira status was transitioned
- Jira status before and after the transition attempt
- whether the Jira test case comment was added
- what still needs verification

## scripts/

- `scripts/transition_issue.sh`: Loads Jira credentials from `~/.zshrc`, resolves the issue key, lists available transitions, moves the issue to the requested status name when available, and optionally posts a Jira comment whose visible text starts with `测试用例：`.
