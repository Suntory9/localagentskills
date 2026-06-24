# Data sources & methodology

How `analyze.py` finds, reads, deduplicates and prices every local AI session.
Read this before changing the engine or explaining a number to the user.

## The three stores

### 1. XDT Maker — SQLite DB (richest metadata + real $ ledger)
Path: `~/Library/Application Support/xdt-maker/xdt-maker-*.db` (pick newest by mtime).
Opened **read-only** (`file:...?mode=ro`). Timestamps are **epoch milliseconds**.
The selected DB path is emitted in warnings / JSON so mismatched local stores are
easy to diagnose.

| table | what we use |
|---|---|
| `daily_spend(day, cost_usd)` | XDT's authoritative **metered cash** per day (its own subscription/discounted rate basis). Shown as a *reference* line only. |
| `sessions(...)` | per-session metadata: `sdk_session_id` (joins to Claude/Codex transcripts), `model`, `effort`, `fast_mode`, `one_m`, `source` (desktop/scheduler/feishu), `orca_role` (worker/lead), `working_dir`, `title`, `total_cost_usd` (XDT's lifetime $ for that session — kept as `lifetime_real` reference, **not** summed). |
| `messages(session_id, agent_meta, created_at)` | `agent_meta` JSON holds per-message `model` + `usage{inputTokens,outputTokens,cacheReadInputTokens,cacheCreationInputTokens}`. Used as a **fallback** token source only for XDT sessions that have no file transcript (e.g. codex workers). Not every message carries meta (coverage varies by install). |
| `schedules` / `schedule_runs` | recurring jobs (cron, model, effort) and their runs in window; we attribute deduped session cost back to each schedule. |
| `orca_workflows` / `orca_workers` | multi-agent workflow grouping (surfaced via `source_type=worker`). |

Important: `sum(sessions.total_cost_usd) == sum(daily_spend)` (verified) — the ledger
is internally consistent, but per-session it is unreliable and uses an unknown
discounted rate. **We never use XDT dollars for the main estimate.**

### 2. Claude Code transcripts — source of truth for ALL Claude usage
Paths: `$CLAUDE_CONFIG_DIR/projects/<slug>/<sessionId>.jsonl` when
`CLAUDE_CONFIG_DIR` is set, plus `~/.config/claude/projects/<slug>/<sessionId>.jsonl`
and `~/.claude/projects/<slug>/<sessionId>.jsonl`. Missing roots are silently
skipped; files are deduped by absolute path and session id. Each assistant line carries
`message.model` + `message.usage` (`input_tokens`, `cache_creation_input_tokens`
with 5m/1h split under `cache_creation`, `cache_read_input_tokens`,
`output_tokens`, `server_tool_use` web search/fetch counts) and an ISO `timestamp`.
Windowed **per message** by timestamp.

**Streaming/duplicate dedup (matters a lot):** Claude Code logs the *same*
assistant message on several lines per turn (often 2–4×) with **identical**
cumulative `usage` — same `message.id`, differing only by timestamp (older logs
have no top-level `requestId`). Summing every line double/triple-counts. We dedupe
by `(message.id, requestId)` — `requestId` optional, so `message.id` alone keys it —
and keep one record per message. In practice this removes a large number of
duplicate rows and can cut the Claude token estimate roughly in half. Lines with
no `message.id` fall back to per-line counting.

The XDT Maker app launches Claude via the SDK (`entrypoint: sdk-ts`) and those
transcripts **also land here**, named by their `sdk_session_id`. We classify each
file: if `sessionId ∈ sessions.sdk_session_id` → source **XDT Maker** (enriched
with DB metadata) — this includes transcripts whose id only matches a historical
`sdkSessionId` in `agent_meta` (resumed/forked sessions); else → source
**Claude Code** (genuine standalone/interactive use).
Files under `*xdt-maker-dialogues*` are an older mechanism and skipped.

### 3. Codex — rollout transcripts
Homes scanned (deduped by realpath): `$CODEX_HOME` (if set), `~/.codex`, and the
XDT-managed codex-home next to the XDT DB (`<xdt app support>/codex-home`, where
XDT's own codex workers write). Under each home: `sessions/**/rollout-*.jsonl` +
`archived_sessions/**/*.jsonl`. Sessions are deduped by session id across homes.
- `session_meta` → session id, cwd, originator.
- `turn_context` → `model` (e.g. `gpt-5.5`), `effort`.
- `event_msg` with `payload.type == "token_count"` → `info.last_token_usage`
  (per-turn delta: `input_tokens`, `cached_input_tokens`, `output_tokens`,
  `reasoning_output_tokens`). We **sum the in-window deltas** (not the cumulative
  `total_token_usage`, which spans the whole resumed lifetime). Non-cached input =
  `input_tokens - cached_input_tokens`; `output_tokens` already includes reasoning
  in local Codex logs, so `reasoning_output_tokens` is retained only as a diagnostic
  and is **not** added again for cost.
- Active `sessions/` files are mtime-prefiltered with a window + 1 day slack.
  `archived_sessions/` files are not mtime-prefiltered; they are scanned by content
  timestamp to avoid missing restored or migrated files with old mtimes.
- **Host attribution (important):** the host (source) is WHERE the rollout
  actually ran — `session_meta.originator` (e.g. "Codex Desktop"/vscode → host
  **Codex**). XDT Maker is an aggregator that *indexes* standalone Codex
  Desktop/CLI sessions into its own DB, so a matching XDT row does NOT mean XDT
  hosted it. A codex rollout is attributed to **XDT Maker** ONLY when its XDT row
  is a genuine orca worker/lead (`orca_role` set → source_type worker/orca-lead);
  otherwise it stays **Codex** (title/project still enriched from the XDT row).
  Do not confuse the *project* a session works on (cwd, e.g. `xdt-maker`) with the
  *host App* — a Codex Desktop session editing the xdt-maker repo is host=Codex,
  project=xdt-maker.
- **Title can be STALE on long resumed sessions (use `project`, not `title`, to say
  what a session did).** A Codex/XDT `title` is frozen at the session's first
  message; a session can be born on project A (its title mentions A) then be
  *resumed* and reused for weeks on project B. The rollout's per-session_meta `cwd`
  (→ `project`) stays correct (B), but the title still says A. Typical shape: a
  long, many-turn, high-cost session whose title names a file/topic from project A
  while every session_meta cwd is project B — it was opened once on A, then reused
  for B. The tokens are real and in-window; only the *title* is misleading (no
  double-count / timestamp bug). The most-expensive-session table therefore shows
  BOTH `项目`(project) and `标题`(title); when summarizing, trust `project`.
- **Service tier (fast/priority pricing):** `codex_priority_turns()` reads
  `~/.codex/logs_2.sqlite` (`logs.feedback_log_body`, the "websocket request:"
  bodies — same source CodexBar uses) for which `turn_id`s ran
  `service_tier:"priority"` vs an explicit standard tier. In `read_codex` each
  token_count event is matched to its `turn_context.turn_id`: priority turns are
  priced at `gpt-5.x-priority` ($12.5/$75/$1.25, 2.5×); turns the logs don't cover
  fall back to the config default (`~/.codex/config.toml` `service_tier` / desktop
  `default-service-tier`). Non-priority turns with >272k input use
  `gpt-5.x-above272k` ($10/$45/$1); priority is flat and overrides the 272k bump.
  All a what-if yardstick — Codex is a flat subscription, so $0 real cash regardless.

### 4. Extended local-log providers (`providers.json`, dispatched by `format`)
These run after the three built-ins via the `FORMAT_READERS` table. All
gracefully no-op when their roots are absent (tool not installed), so they are
safe to ship enabled. Formats below were verified against steipete/CodexBar's
scanners (we ported the format knowledge, not the code).

- **`pi_jsonl` → `read_pi()`** — Pi, `~/.pi/agent/sessions/**/*.jsonl` (`$PI_HOME`
  override). Per CodexBar `PiSessionCostScanner`: a `model_change` line sets the
  current `(provider, model)`; each `message` with `message.role=="assistant"`
  carries `message.usage` (many aliases: input/inputTokens/input_tokens/…,
  cacheRead…, cacheWrite/cacheCreation…, output…). Pi proxies upstreams, so we
  price by the upstream FAMILY: `openai-codex`→gpt-5.x (cache-write folded into
  input, matching how Codex bills), `anthropic`→claude (cache-write priced
  separately). A row whose provider tag is present but **unmapped is dropped** (we
  won't guess a price; count surfaced in warnings). Timestamp is epoch-s /
  epoch-ms / ISO. Pi's own plan = subscription (per-session billing override).
- **`opencode_sqlite` → `read_opencode_sqlite()`** — OpenCode-Go,
  `~/.local/share/opencode/opencode.db` (`$OPENCODE_DATA`). The DB stores a
  **pre-computed USD `cost`** per assistant message (`json_extract(data,'$.cost')`,
  `role=assistant`, `providerID=opencode-go`), NOT a token breakdown — so we book
  the dollars directly, tokens stay 0, and these sessions don't appear in token
  charts. Real spend → metered.
- **`generic_jsonl` → `read_generic_jsonl()`** — config-only adapter for any tool
  that writes per-message token usage to JSONL. `fields` values are dotted paths
  OR **alias lists** (first present wins); `type_key/type_value` filters rows; `ts`
  omitted → window by file mtime; `cached_in_input:true` subtracts cache from
  input; per-entry `billing` overrides model-derived billing. One `Sess` per file.
- **`openclaw` → `read_openclaw()`** — the OpenClaw multi-agent framework
  (`~/.openclaw`, `$OPENCLAW_HOME`). Two deduped data sources, one source label
  ("OpenClaw"):
  1. **Nested codex-homes** `agents/<agent>/agent/codex-home/` are *standard Codex
     rollout stores* → parsed by the shared `_parse_codex_file()` with per-home
     priority (each home's own `logs_2.sqlite`) and `config.toml` tier. This is
     authoritative for codex-backed turns.
  2. **Native session logs** `agents/<agent>/sessions/*.jsonl` — both the trajectory
     event schema (`type:"model.completed"`, `data.usage{input,output,cacheRead}`)
     and the newer message log (`model_change` ctx + `type:"message"` →
     `message.usage`). Rows whose provider is `openai-codex`/`openai` are SKIPPED
     here because the same turns are already in #1 (the trajectory is OpenClaw's own
     trace of the underlying Codex run) — this is the key dedup that prevents
     double-counting; only non-Codex backends (anthropic/bedrock/…) are booked.
     `billing:""` ⇒ derive per model family. Since OpenClaw's data is usually on a
     different machine, run the engine there (it's pure stdlib).

**Per-session billing override**: `Sess.billing` (set by Pi/OpenCode/generic
entries) wins over the model-family-derived `billing_of()`. `sess_billing(s)` is
the accessor used everywhere a session's metered-vs-subscription split matters.
This exists because some tools' billing is a property of the TOOL (Pi's plan),
not the model it proxies.

## Deduplication order (avoids triple counting)
1. `read_xdt_context` — load metadata + ledger + schedules (no token cost yet).
2. `read_claude` — every transcript; mark each XDT-owned `sdk` in `seen_sdk`.
3. `read_codex` — every rollout; XDT-owned ones marked in `seen_sdk` too.
4. `read_xdt_agent_meta_fallback` — only XDT sessions whose `sdk ∉ seen_sdk`
   (fills codex-worker / pruned-transcript gaps from `agent_meta`).

## Cost methodology
`cost = Σ token_class × rate(model, class) / 1e6`, rates from `pricing.json`
(public **API list prices**). This is a **uniform yardstick** — token counts are
provider-logged ground truth; pricing is an explicit, editable assumption.

**Pricing-source rule (non-negotiable):** rates come ONLY from `pricing.json`
(local price-of-record) or, for an unknown/new model, an official lookup — never
from the model's own memory. Authoritative sources: if an XDT Maker source tree is
available locally, its own cc-code model-cost table for Claude models (a manually
maintained table sourced from platform.claude.com/pricing — no live API, no Codex
pricing); otherwise the vendor pricing pages (Anthropic / OpenAI / Google / xAI /
DeepSeek) via web search. `analyze.py` emits an `UNKNOWN MODEL PRICING` warning when a
model hits the `_default` fallback — resolve it (and refresh all rates while you're
at it) before trusting the dollars. See SKILL.md for the full procedure.

Why not use XDT's metered `$`? Because it (a) only covers XDT, not CLI/Codex,
(b) uses an opaque discounted rate that runs ~5–10× below list for cache-heavy
sessions, and (c) is unreliable per-session. The uniform token estimate is the
correct lens for *relative* "where is consumption / waste" questions. We still
print XDT's ledger as the real-cash anchor.

Expect `total_est` ≫ `xdt_ledger_real`. That gap is the subscription discount,
not a bug. Always explain this to the user.

## Waste heuristics (tunable in `main()` cfg)
- **low_cache**: turns > 1, cost ≥ $1 and >50k input tokens but cache reuse rate
  < 50% → context re-sent uncached. This is a cache reuse ratio, not a strict
  provider hit-rate; first turns are excluded because they build cache.
- **downgrade**: premium model (opus / gpt-5.x), high/xhigh effort, tiny output
  (<3k), few turns (≤6), cheap (<$0.50) → a downgrade candidate that needs human
  confirmation before changing model or effort.
- **runaway**: cost > 6× median and ≥ $5 → inspect for loops / runaway automation.
  (Note: the old `one_m` / 1M-context waste flag was REMOVED — Opus 4.x and
  Sonnet 4.6 now include the full 1M window at standard rate, so 1M is no longer
  a pricing premium.)

## Known caveats
- Prices in `pricing.json` are vendor list prices and go stale fast — they were
  verified 2026-06-04 (Opus 4.x $5/$25, GPT-5.5 $5/$30, Sonnet 4.6 $3/$15, Haiku
  4.5 $1/$5). Re-verify online before trusting absolute dollars; a wrong rate
  silently distorts the whole ranking (opus vs gpt-5.x is the sensitive pair).
- `agent_meta` covers only a subset of messages → fallback sessions may slightly under-count.
- `daily_spend` for *today* may not be flushed yet; token estimate still counts it.
  Session rows use a rolling 24h window, while the ledger is natural-day based and
  includes days that overlap the window boundary.
- XDT "dialogue" sessions are projectless chats stored under per-session UUID
  folders (`.../xdt-maker/dialogues/<date>/<uuid>`); `basename_project()` collapses
  them into the single bucket `(XDT 对话·无代码项目)` (the title carries meaning,
  not the path). Other UUID cwds fall back to the nearest non-UUID ancestor folder.
  In the by-project table this is adaptive: an individually expensive projectless
  session (≥ `cfg["dialogue_breakout_cost"]`, default $2) is broken out by its
  title so a costly chat isn't hidden inside the bucket; cheap ones stay merged.
- JSON / Markdown artifacts include session titles, paths and ids; treat them as
  sensitive local diagnostics, not public material.
- A session id appearing in multiple files (active + archived, or two Codex/Claude
  homes) is deduped at the **file** level — first by path order wins. Correct when
  the copies are identical (the normal case; typically 0 such duplicates). It is
  NOT yet merged per-event, so a session genuinely *split* across
  files with differing in-window content could be under-counted. Revisit with
  per-event `(timestamp, token-tuple)` merge if that case ever appears.

## Out of scope (intentionally not supported)

The skill only covers tools that write **reliable local per-token data**. Tools
that expose usage *only* through an authenticated quota API/cookie — output is
"% of plan" / "$ balance", not tokens — are deliberately excluded: **Gemini CLI,
Amp, Grok, DeepSeek, Cursor, Copilot, Windsurf** (full reasons in
`providers.json` → `_not_supported`). A quota framework for these was built and
then **removed** on purpose: the numbers aren't token-cost, the auth (cookies /
app tokens) is brittle and expires, and per-vendor maintenance isn't worth it for
a local, read-only, no-network tool.

The instructive case is **Cursor**: its local `state.vscdb` (`cursorDiskKV`,
`bubbleId:* → tokenCount`) has tokens **only for chat-mode** bubbles — agent-mode
bubbles are `0` — and the server exposes **no tokens at all**, only monthly
dollars/percent behind a `cursor.com` cookie (CodexBar's own descriptor sets
`supportsTokenCost:false` for Cursor). So there is no reliable token figure to be
had; it was dropped rather than report a partial/fabricated number.

**Rule:** before adding any tool, inspect its actual on-disk data (`find` / open
the sqlite). Only wire it up if it has genuine per-message token counts; if all it
has is a quota/balance endpoint, leave it out.

## Coverage map (transparency for general use)
`provider_coverage()` builds one row per known token-cost provider and the report
renders a "覆盖范围(本机探测的工具)" table: `有数据` (contributed in window),
`已装·窗口内无数据` (installed but no usage this window), `未安装` (roots absent),
`未启用` (disabled in registry). `provider_installed()` does the on-disk presence
check (built-ins via their root logic; config formats via `roots`). The point: the
report shows WHAT WAS CHECKED, not just what was found — so a new user can confirm
their tool is covered (or see why it shows nothing). Entries with
`format_verified:false` are tagged "(未核实格式)" when present.

## Provenance: CodexBar cross-check (2026-06-04)
The provider classification (which tool is a local-log token-cost source vs a
quota-only monitor) and every on-disk format/field path was verified against
steipete/CodexBar's source. Only **Codex, Claude (+Vertex view), Pi** parse local
per-token JSONL; **OpenCode-Go** reads a local sqlite for pre-computed USD; Grok's
local `signals.json` holds unpriced token counts (CodexBar never costs it);
everything else (Gemini, Amp, DeepSeek, OpenCode-web, Cursor, Copilot, Windsurf,
+~40 more) is quota/balance-only. CodexBar prices via models.dev with a hardcoded
fallback table; we use the curated `pricing.json` + the web-verify rule instead
(no runtime models.dev dependency), which is why our gpt-5.x priority/272k tiers
were cross-validated against CodexBar's `CostUsagePricing.swift`.
