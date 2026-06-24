---
name: jira-proto-to-main
description: >-
  Given a Jira issue such as TTDBL-42165, locate the corresponding proto
  commits in /Users/songdc/zserver/proto/pb/game, port the client-relevant
  proto changes into the Unity project, align affected Lua call sites when
  needed, then hand off to jira-unity-to-main style trunk submission. Use when
  a Jira ticket primarily lands in the proto submodule first and the Unity
  client needs the matching protocol updates on trunk.
---

# Jira Proto To Main

## Overview

Use this skill when the input is usually a Jira key and the real source of truth
for the change lives in the proto submodule:

- source repo: `/Users/songdc/zserver/proto/pb/game`
- target repo: current Unity project
- final submission target: trunk branch through
  [$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md)

This skill is for protocol synchronization work, not for generic Unity feature
implementation.

## What This Skill Should Do

1. Normalize the Jira input.
   Accept either a Jira key like `TTDBL-42165` or a full Jira URL.

2. Read the Jira issue first.
   Reuse the same Jira-reading flow as
   [$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md).
   The Jira summary is still the source of the final commit title.

3. Find matching proto commits in `zserver/proto/pb/game`.
   Prefer searching commit history by Jira key first.

4. Inspect the net proto effect before editing Unity files.
   When multiple commits belong to the same Jira, prefer one net diff over
   reading every commit in isolation.

5. Port only the client-relevant changes into the Unity project.
   Usually this means files under:

- `Assets/Config/ttdbl2_protobuf/*.proto.txt`
- related Lua files under `Assets/Scripts/LuaScript/Service`
- related Lua files under `Assets/Scripts/LuaScript/Pb`
- any directly affected data or view logic

6. Validate the call sites that depend on the changed fields.
   Do not stop at editing `.proto.txt` if the Lua code is now out of sync.

7. Submit to trunk using the same commit-title rule and submission discipline as
   [$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md).

## Workflow

### 1. Normalize Jira Input

Accept:

- `TTDBL-42165`
- `https://xindong.atlassian.net/browse/TTDBL-42165`

Extract the Jira key and use it consistently for history search and final
commit title generation.

### 2. Read Jira Before Touching Code

Load Atlassian credentials first:

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; env | grep ATLASSIAN_'
```

Then read the issue with the existing script from
[$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md):

```bash
zsh -lc 'source ~/.zshrc >/dev/null 2>&1; /Users/songdc/.codex/skills/jira-unity-to-main/scripts/read_issue.sh TTDBL-42165'
```

### 3. Find Proto Commits in the Submodule

Search commit history in the proto repo:

```bash
git -C /Users/songdc/zserver/proto/pb/game log --oneline --grep='TTDBL-42165'
```

If needed, widen the search:

```bash
git -C /Users/songdc/zserver/proto/pb/game log --oneline --all --grep='TTDBL-42165'
```

When the Jira has more than one relevant commit, collect all related SHAs before
editing Unity files.

### 4. Inspect the Net Proto Effect

For a single commit:

```bash
git -C /Users/songdc/zserver/proto/pb/game show --stat <sha>
git -C /Users/songdc/zserver/proto/pb/game show <sha> -- cat.proto.txt
```

For multiple commits that touch the same proto file, prefer the net diff:

```bash
git -C /Users/songdc/zserver/proto/pb/game diff <first_sha>^ <last_sha> -- cat.proto.txt
```

This is usually the fastest way to answer:

- which fields were added
- which fields were removed
- which field numbers changed
- whether only one client file needs syncing or several do

### 5. Port the Client-Relevant Files

Common target files in Unity:

- `Assets/Config/ttdbl2_protobuf/cat.proto.txt`
- `Assets/Config/ttdbl2_protobuf/common.proto.txt`
- `Assets/Config/ttdbl2_protobuf/protoid.proto.txt`

Do not assume only one file is affected. Check the proto commit diff first.

### 6. Validate Lua Usage After Proto Sync

After updating `.proto.txt`, inspect the Unity client for impacted usage:

```bash
rg -n 'InCatGeneUpLv|OutCatGeneUpLv|InCatSetAutoCompose|OutCatSetAutoCompose|materialAuto|auto =' Assets/Config/ttdbl2_protobuf Assets/Scripts/LuaScript
```

Use the actual message names and fields from the Jira at hand, not only the cat
example above.

Check at least:

- service request packing
- response parsing
- pb route registration
- any data/view logic that consumes the changed fields

If the Lua side is already aligned, say so explicitly and keep the diff small.

### 7. Validate Locally

Prefer lightweight validation:

- `luac -p` on changed Lua files
- targeted `rg` checks for removed fields still being referenced
- Unity refresh if needed

If no safe runtime validation is available, state that clearly.

### 8. Submit to Trunk

Once the Unity-side proto sync is correct, finish with
[$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md).

Commit title format:

```text
<JIRA_KEY><summary>
```

Example:

```text
TTDBL-42165【猫猫包风味升级优化】【前后端】
```

Default target branch:

- `2023-11-28-Unity2021-3-13`

Do not include newly created requirement or dev-plan markdown files in the trunk
submission unless the user explicitly asks for that.

## Guardrails

- Never hand-edit proto changes before confirming what actually changed in
  `zserver/proto/pb/game`.
- Never sync only the `.proto.txt` file if the corresponding Lua request or
  response logic is now incompatible.
- Never guess the Jira summary; read it and reuse it for the commit title.
- Never stage the whole repo when the changed file set is known.
- Never submit `TTDBL-xxxx*.md`, temporary notes, or dev-plan markdown files to
  trunk by default.
- If more than one proto commit matches the Jira, inspect the combined net diff
  before deciding what to port.

## Quick Commands

Find commits:

```bash
git -C /Users/songdc/zserver/proto/pb/game log --oneline --all --grep='TTDBL-42165'
```

Inspect a single commit:

```bash
git -C /Users/songdc/zserver/proto/pb/game show 5bebcfd68ce3ec822e017255759d34e1f49fa3f9 -- cat.proto.txt
```

Inspect the net effect across two commits:

```bash
git -C /Users/songdc/zserver/proto/pb/game diff 5bebcfd68ce3ec822e017255759d34e1f49fa3f9^ 3ca352194b907dc9b4d51710c9de443591b78795 -- cat.proto.txt
```

Check Unity-side usage:

```bash
rg -n 'InCatGeneUpLv|InCatSetAutoCompose|OutCatSetAutoCompose|materialAuto|auto =' Assets/Config/ttdbl2_protobuf Assets/Scripts/LuaScript
```

## Example

For a Jira like `TTDBL-42165`, if the proto repo has two related commits:

- `5bebcfd68ce3ec822e017255759d34e1f49fa3f9`
- `3ca352194b907dc9b4d51710c9de443591b78795`

the expected execution pattern is:

1. read Jira
2. confirm these are the relevant proto commits
3. inspect the net diff in `cat.proto.txt`
4. sync Unity `cat.proto.txt`
5. confirm Lua service code is aligned
6. submit through
   [$jira-unity-to-main](/Users/songdc/.codex/skills/jira-unity-to-main/SKILL.md)
