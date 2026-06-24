# Cherry-Pick Guidelines

Use this reference when a commit-port task is not obviously safe.

## Good cherry-pick candidates
- A small isolated bug fix.
- A self-contained feature toggle change.
- A commit touching only one narrow subsystem.
- A commit whose changed files all exist on the target branch.
- A commit with no obvious dependency on recent refactors.

## Risky cherry-pick candidates
- Commits that follow a large refactor.
- Commits that rename or move files.
- Commits that modify generated files plus their source inputs.
- Commits that change protocols, schemas, migrations, or API contracts.
- Commits that mix feature work, cleanup, and refactor in one SHA.
- Merge commits.
- Commits that depend on assets, configs, or prefabs not present on the target branch.

## Usually better handled by manual porting
- The target branch has the same area but different architecture.
- The original bug does not reproduce the same way on the target branch.
- The source commit depends on too many precursor commits.
- The source commit contains broad formatting or mechanical churn hiding a small logic fix.

## Dependency checks
Before cherry-picking, inspect:
- previous 3 to 10 commits in the same area
- whether introduced symbols already exist on target branch
- whether referenced files exist on target branch
- whether config, proto, migrations, or assets changed together
- whether the local target branch is behind remote

Helpful commands:

```bash
git fetch --all --prune
git show --stat <sha>
git show --name-only <sha>
git log --oneline -- <path>
git grep '<symbol>'
git branch --contains <sha>
git branch -vv
```

## Sync before porting
Do not assume the correct first step is `git pull`.

Preferred order:
1. `git fetch --all --prune`
2. inspect whether the target branch is behind remote
3. decide whether to sync before porting

Use `git pull` only when justified.

Preferred sync choices:
- `git pull --ff-only` when the branch can fast-forward cleanly
- `git pull --rebase` only when that matches the user's workflow
- stop and ask when syncing changes the risk profile significantly

If the branch is current enough and the user only wants a local port, you may skip pull.

## Merge commit handling
Avoid automatic handling.

Why it is risky:
- `git cherry-pick -m` needs the correct parent selection.
- Picking the wrong parent can import the wrong side of the merge.
- A merge commit may bundle multiple logical changes that should not move together.

Default rule:
- stop and ask for confirmation before using `git cherry-pick -m`

## Conflict interpretation
Conflicts are signals, not just obstacles.

Common meanings:
- source and target implemented the same idea differently
- target branch is missing prerequisite commits
- a refactor changed the integration point
- file moves or renames changed context too much

If conflicts happen:
1. list all conflicted files
2. identify whether the conflict is logic, file movement, or generated output
3. inspect the surrounding code before choosing `ours` or `theirs`
4. prefer manual resolution over blanket replacement

Useful commands:

```bash
git status
git diff --name-only --diff-filter=U
git checkout --ours -- <path>
git checkout --theirs -- <path>
git add <path>
git cherry-pick --continue
git cherry-pick --abort
```

## Signs that target already has the change
- `git branch --contains <sha>` shows the target branch
- same logic already exists under a different SHA
- only formatting or line movement differs
- a previous manual port already landed the same fix

Do not duplicate the change. Report that the target likely already contains it.

## Validation checklist after cherry-pick
- confirm the intended files changed
- compare diff size with the source commit
- inspect critical logic paths manually
- run the smallest relevant tests or build checks
- verify no companion config or generated file was missed

## Recommended operating modes

### Analysis-only mode
Use when:
- commit dependencies are unclear
- target branch is sensitive
- merge commit is involved
- user asked for a recommendation first

Output:
- recommended commit set
- portability assessment
- key risks
- suggested commands

### Safe execution mode
Use when:
- the request is clear
- worktree is clean
- the commit is not a merge commit
- dependencies are understood

Preferred sequence:
1. fetch remote state
2. decide whether sync is needed
3. switch to target branch
4. create a temporary branch
5. cherry-pick
6. resolve intentionally if needed
7. run minimal validation
8. push only if the user requested it
9. summarize result

## Branch safety advice
- Avoid applying directly to long-lived protected branches unless the user explicitly asks.
- Prefer a temporary branch named like `codex/port-<topic>`.
- Never force-push unless the user explicitly requests it.
- Never reset or discard unrelated work without explicit approval.
- Do not auto-push after cherry-pick unless the user asked for it.
