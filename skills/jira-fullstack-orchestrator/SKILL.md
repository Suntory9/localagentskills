---
name: jira-fullstack-orchestrator
description: Use this skill when a Jira-driven feature needs coordinated planning and execution across multiple repos such as backend and client. It organizes work into orchestrator, server-exec, and client-exec modes, keeps a shared implementation plan, splits tasks by repo, defines integration checkpoints, and standardizes progress/verification handoff between a control thread and repo-specific execution threads.
---

# Jira Fullstack Orchestrator

Use this skill for cross-repo feature delivery where one Jira issue spans multiple codebases and needs a single execution rhythm.

Typical cases:
- one Jira issue requires backend and client changes
- the user wants a single implementation plan before coding
- the user wants repo-specific execution with a shared source of truth
- the user wants progress summaries, integration checkpoints, or weekly/status rollups for one feature

Do not use this skill for:
- single-repo tasks with no coordination needs
- isolated bug fixes that do not need orchestration
- pure reporting tasks with no execution planning

## Default document outputs

When this skill is used in `orchestrator` mode, create and maintain these Markdown files by default:

- `/Users/songdc/Documents/Playground/jira-orchestrator/<JIRA_KEY>.md`
- `/Users/songdc/Documents/Playground/jira-orchestrator/<JIRA_KEY>-zserver.md`
- `/Users/songdc/Documents/Playground/jira-orchestrator/<JIRA_KEY>-ttdbl2_unity.md`

Purpose:
- the main file keeps the shared source of truth
- the repo files keep execution-specific details

Update the files instead of creating new ad hoc notes for the same Jira issue.
If only one repo is involved, the main file is still required and the repo-specific file is optional.

## Core idea

Treat the work as three coordinated roles:

1. `orchestrator`
2. `server-exec`
3. `client-exec`

The skill can run from any thread. It is not bound to `Playground`.

Choose the role from the current repo context:
- in neutral or planning directories such as `Playground`, default to `orchestrator`
- in backend repos such as `zserver`, default to `server-exec`
- in client repos such as `ttdbl2_unity`, default to `client-exec`

If the user explicitly says `先做服务端`, `先做客户端`, or `只给我总控方案`, follow that instead of auto-detection.

## Role outputs

### 1. `orchestrator`

Use in a control thread to create and maintain the shared plan.

Always try to produce:
- issue summary
- repo split
- dependency order
- interface and field checkpoints
- integration checklist
- acceptance checklist
- current blockers
- next actions

Default workflow:
1. Read Jira and any linked docs.
2. If Jira description contains readable links, follow them by default.
3. Create or update the default document outputs.
4. Identify affected repos.
5. Split work into backend, client, and integration items.
6. Mark what can start in parallel and what is blocked on contract stability.
7. Define the exact handoff each execution thread should report back.

### 2. `server-exec`

Use in the backend repo thread.

Focus only on backend execution:
- protocol and schema changes
- defaults and persistence
- business rules
- minimal verification
- backend-facing delivery summary

Always try to produce:
- backend target
- affected files/modules
- implementation order
- verification performed or skipped
- client impact summary
- what changed in contract terms

Do not expand into detailed client UI design unless needed to explain a contract decision.

### 3. `client-exec`

Use in the client repo thread.

Focus only on client execution:
- protocol/service access
- data-layer adaptation
- shared local rule helpers
- view/UI/prefab logic
- minimal verification
- client-facing delivery summary

Always try to produce:
- client target
- affected files/modules
- dependency on backend contracts
- what can be built with mock data
- what needs real backend data to finish
- verification performed or skipped

Do not redesign backend rules locally. Treat backend contracts as the authority once confirmed.

## Standard operating model

Use this sequence unless the user explicitly wants a different order.

1. Control thread:
   create a one-page implementation sheet with:
   - goal
   - backend tasks
   - client tasks
   - integration points
   - acceptance points

2. Backend thread:
   lock contracts first:
   - interfaces
   - fields
   - defaults
   - rule boundaries

3. Control thread:
   publish the backend contract summary for the client thread.

4. Client thread:
   build no-regret pieces early:
   - service hooks
   - data-layer adapters
   - UI shell
   - placeholders and state transitions

5. Integration:
   connect real data only after contract stability.

6. Control thread:
   summarize:
   - done
   - not done
   - blockers
   - validation status
   - next step

The implementation sheet should be written to the main orchestrator document, not only returned in chat.

## Required habits

### Follow Jira links by default

If Jira description contains a Confluence or other internal requirement link and it is readable from the local credential path, read it automatically. Do not stop at “description only contains a link”.

### Re-read requirement docs when they change

If the Jira description, linked Confluence page, or any requirement doc changes for the same Jira key, treat it as a controlled change event.

Use this order:
1. re-read the latest Jira and linked requirement docs
2. compare against the existing orchestrator documents
3. identify exactly what changed in:
   - rules
   - interfaces and fields
   - acceptance criteria
   - backend/client boundary
4. update the main orchestrator document first
5. update repo-specific execution documents second
6. mark whether existing code is:
   - unaffected
   - partially affected
   - needs rework
   - needs re-validation
7. only then continue execution

Do not continue coding from stale assumptions after a requirement change.

### Keep one source of truth for rules

For rule-heavy features:
- backend keeps one authoritative execution path
- client keeps one authoritative local preview/helper path
- views should not duplicate complex business rules

When you see the same rule duplicated in multiple UI entry points, prioritize moving it into a shared data/helper layer.

### Prefer contract-first parallelism

Parallelize only after the contract is stable enough.

Safe client-parallel items:
- UI shell
- node structure
- service stubs
- placeholder states
- local state wiring

Unsafe items before contract stability:
- exact result rendering
- edge-case behavior
- local recreation of backend settlement logic

### Enforce submission hygiene

Before commit/push in execution threads:
1. define intended file list
2. compare against actual changed file list
3. exclude unrelated files
4. state what verification was run

### Separate orchestration from execution

Use the control thread to think and coordinate.
Use repo threads to code and validate.
Do not mix large backend and client code changes in one thread unless the user explicitly prefers that tradeoff.

### Always state the next step

After finishing any meaningful step, always tell the user what should happen next.

At minimum, include one explicit next action such as:
- continue in `zserver`
- continue in `ttdbl2_unity`
- update the orchestrator document
- start integration verification
- re-read the updated requirement doc

This applies to:
- planning outputs
- backend execution summaries
- client execution summaries
- integration summaries
- requirement-change summaries

The goal is to prevent context loss and reduce the chance that work stalls between steps.

## Output templates

### Orchestrator template

Use this shape:

- Issue summary
- Source links
- Repo split
- Execution order
- Parallelizable work
- Integration checkpoints
- Acceptance checklist
- Risks and blockers
- Next actions
- Current status

When the requirement changed, also include:
- Change impact
- Rework needed

### Server-exec template

Use this shape:

- Backend goal
- Files/modules
- Contract changes
- Implementation steps
- Verification
- Client handoff
- Next action

### Client-exec template

Use this shape:

- Client goal
- Files/modules
- Backend dependencies
- Implementation steps
- Verification
- Control-thread handoff
- Next action

## Recommended repo mapping

Common example:
- `Playground` or neutral planning thread: `orchestrator`
- `zserver`: `server-exec`
- `ttdbl2_unity`: `client-exec`

Treat this as a default, not a hard requirement.

## Success criteria

This skill is working well when:
- the user gets one coherent plan for a multi-repo feature
- backend and client threads have clear boundaries
- integration points are known before late-stage testing
- progress summaries are easy to produce
- unrelated files do not leak into commits
- the current Jira state can be recovered from the maintained Markdown files without reading chat history
