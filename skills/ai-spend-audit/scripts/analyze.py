#!/usr/bin/env python3
"""
ai-spend-audit: analyze recent AI token consumption & cost across every local
session store (XDT Maker, Claude Code CLI, Codex), estimate dollars at a uniform
yardstick, and flag waste / optimization opportunities.

Usage:
    python3 analyze.py [--days N] [--end YYYY-MM-DD] [--top N]
                       [--pricing PATH] [--out DIR] [--json] [--quiet]

Methodology (read references/data-sources.md for the full story):
- Cost is computed UNIFORMLY from token counts x pricing.json (public API list
  prices), windowed by per-message timestamp. Token counts are ground truth
  (logged by the providers); pricing is a transparent, editable assumption.
- Sources are DEDUPLICATED by session id. ~/.claude transcripts are the source
  of truth for all Claude usage; a transcript whose id is an XDT `sdk_session_id`
  is attributed to "XDT Maker" (not double-counted). Codex rollouts are the
  source of truth for Codex; XDT codex-worker rollouts fold into XDT.
- XDT Maker also keeps its own metered ledger (daily_spend / total_cost_usd).
  That ledger uses XDT's own (subscription/discounted) rate basis and runs well
  below API list price; we show it separately as a reference, never mixed into
  the uniform estimate.
- Read-only: the XDT DB is opened mode=ro; jsonl files are streamed.
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
try:
    import tomllib
except ImportError:
    tomllib = None
from collections import defaultdict
from datetime import datetime, timezone

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

HOME = os.path.expanduser("~")
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Pricing                                                                      #
# --------------------------------------------------------------------------- #
def load_pricing(path):
    with open(path) as f:
        data = json.load(f)
    models = data.get("models")
    if not isinstance(models, dict):
        raise KeyError("models")
    return models


def model_key(model, pricing):
    if not model:
        return "_default"
    m = model.lower()
    if m in pricing:
        return m
    if "opus" in m:
        return "claude-opus-4"
    if "sonnet" in m:
        return "claude-sonnet-4"
    if "haiku" in m:
        return "claude-haiku-4"
    if "codex" in m:
        return "gpt-5-codex"
    if m.startswith("gpt-5.5"):
        return "gpt-5.5"
    if m.startswith("gpt-5"):
        return "gpt-5"
    if "gemini" in m:
        return "gemini-flash" if "flash" in m else "gemini-pro"
    if "grok" in m:
        return "grok"
    if "deepseek" in m:
        return "deepseek"
    return "_default"


def cost_of(tok, model, pricing):
    p = pricing.get(model_key(model, pricing), pricing["_default"])
    return (tok.get("input", 0) * p["input"]
            + tok.get("output", 0) * p["output"]
            + tok.get("cache_read", 0) * p["cache_read"]
            + tok.get("cache_write_5m", 0) * p["cache_write_5m"]
            + tok.get("cache_write_1h", 0) * p["cache_write_1h"]) / 1_000_000.0


def empty_tok():
    return {"input": 0, "output": 0, "cache_read": 0,
            "cache_write_5m": 0, "cache_write_1h": 0}


def add_tok(dst, src):
    for k in dst:
        dst[k] += src.get(k, 0)


def billable_input(t):
    return t["input"] + t["cache_read"] + t["cache_write_5m"] + t["cache_write_1h"]


def cache_ratio(t):
    bi = billable_input(t)
    return (t["cache_read"] / bi) if bi else 0.0


def total_tokens(t):
    return billable_input(t) + t["output"]


def accrue(s, t, model, pricing, ts):
    """Fold one message's token dict into a session: tokens, turn, cost, span."""
    add_tok(s.tok, t)
    s.turns += 1
    s.est_cost += cost_of(t, model, pricing)
    s.first_ts = min(s.first_ts or ts, ts)
    s.last_ts = max(s.last_ts or ts, ts)


# --------------------------------------------------------------------------- #
# Session record                                                              #
# --------------------------------------------------------------------------- #
class Sess:
    __slots__ = ("source", "id", "title", "model", "model_key", "project",
                 "source_type", "tok", "est_cost", "lifetime_real", "turns",
                 "first_ts", "last_ts", "one_m", "effort", "fast_mode",
                 "web_searches", "web_fetches", "reasoning_output",
                 "schedule_id", "schedule_name", "flags", "billing")

    def __init__(self, source, sid):
        self.source = source
        self.id = sid
        self.title = ""
        self.model = ""
        self.model_key = "_default"
        self.project = ""
        self.source_type = ""
        # Per-session billing override ("metered"/"subscription"). Empty = derive
        # from the model family via billing_of(). Set by providers whose billing
        # mode is a property of the TOOL, not the model (e.g. Pi's own plan).
        self.billing = ""
        self.tok = empty_tok()
        self.est_cost = 0.0
        self.lifetime_real = None     # XDT's own ledger figure (reference only)
        self.turns = 0
        self.first_ts = None
        self.last_ts = None
        self.one_m = False
        self.effort = ""
        self.fast_mode = False
        self.web_searches = 0
        self.web_fetches = 0
        self.reasoning_output = 0
        self.schedule_id = ""
        self.schedule_name = ""
        self.flags = []

    @property
    def cost(self):
        return self.est_cost

    @property
    def duration_min(self):
        if self.first_ts and self.last_ts and self.last_ts > self.first_ts:
            return (self.last_ts - self.first_ts) / 60.0
        return 0.0


def basename_project(wd):
    if not wd:
        return "(none)"
    wd = wd.rstrip("/")
    low = wd.lower()
    # XDT "dialogue" sessions are projectless chats stored under a per-session
    # UUID folder — collapse them into one readable bucket (title carries meaning,
    # not the path).
    if "/xdt-maker/dialogues/" in low:
        return "(XDT 对话·无代码项目)"
    if "/.slock/agents/" in low:
        return "(slock agent·无代码项目)"
    b = os.path.basename(wd)
    if UUID_RE.match(b):
        # cwd basename is a UUID — fall back to the nearest meaningful ancestor.
        for p in reversed(wd.split("/")):
            if p and not UUID_RE.match(p):
                return p
        return "(无项目)"
    return b or wd


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def populate_session_from_meta(s, meta):
    """Apply XDT session metadata onto a Sess (call only when meta exists)."""
    s.title = meta["title"]
    s.one_m = meta["one_m"]
    s.effort = meta["effort"]
    s.fast_mode = meta["fast_mode"]
    s.lifetime_real = meta["lifetime_real"]
    s.project = meta["project"]
    s.source_type = meta["source_type"]


# --------------------------------------------------------------------------- #
# XDT Maker context (metadata + ledger), NOT token costs                       #
# --------------------------------------------------------------------------- #
def find_xdt_db():
    cands = [c for c in glob.glob(os.path.join(
        HOME, "Library/Application Support/xdt-maker/xdt-maker-*.db"))
        if not c.endswith(("-wal", "-shm"))]
    return max(cands, key=os.path.getmtime) if cands else None


def classify_source_type(source, orca_role):
    if orca_role:
        return "worker" if orca_role == "worker" else "orca-lead"
    if source == "scheduler":
        return "scheduler"
    if source == "feishu":
        return "feishu"
    return "desktop"


def open_xdt_db(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def read_xdt_context(cutoff_s, end_s, warnings):
    """Returns dict: meta_by_sdk, sid_to_sdk, daily_real, sdef, runs, db_path."""
    ctx = {"meta_by_sdk": {}, "sid_to_sdk": {}, "daily_real": {},
           "sdef": {}, "runs": [], "db_path": None}
    db = find_xdt_db()
    if not db:
        warnings.append("XDT Maker DB not found.")
        return ctx
    ctx["db_path"] = db
    warnings.append(f"XDT DB selected: {db}")
    cut_ms, end_ms = int(cutoff_s * 1000), int(end_s * 1000)
    try:
        con = open_xdt_db(db)
    except sqlite3.Error as e:
        warnings.append(f"XDT DB open failed: {e}")
        return ctx

    try:
        for r in con.execute("SELECT day, cost_usd FROM daily_spend"):
            try:
                d_s = datetime.strptime(r["day"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc).timestamp()
            except (ValueError, TypeError):
                continue
            if cutoff_s <= d_s + 86399 and d_s <= end_s:
                ctx["daily_real"][r["day"]] = r["cost_usd"]
    except sqlite3.Error as e:
        warnings.append(f"daily_spend read failed: {e}")

    try:
        table_cols = {r["name"] for r in con.execute("PRAGMA table_info(sessions)")}
        required = {"id", "sdk_session_id"}
        if not required.issubset(table_cols):
            missing = ", ".join(sorted(required - table_cols))
            warnings.append(f"sessions missing required columns ({missing}); XDT dedupe disabled.")
        else:
            wanted = [
                "id", "sdk_session_id", "title", "model", "effort", "fast_mode",
                "one_m", "total_cost_usd", "agent_kind", "orca_role", "source",
                "working_dir", "created_at", "updated_at",
            ]
            optional_missing = [c for c in wanted if c not in table_cols and c not in required]
            if optional_missing:
                warnings.append("sessions missing optional columns: "
                                + ", ".join(optional_missing) + "; defaults used.")
            select_cols = [c for c in wanted if c in table_cols]
            query = "SELECT " + ", ".join(select_cols) + " FROM sessions"

            def rv(row, name, default=None):
                return row[name] if name in row.keys() and row[name] is not None else default

            for r in con.execute(query):
                sdk = rv(r, "sdk_session_id")
                xdt_id = rv(r, "id", "")
                if not xdt_id:
                    continue
                lifetime = rv(r, "total_cost_usd")
                lifetime_real = float(lifetime) if lifetime is not None else None
                source = rv(r, "source")
                orca_role = rv(r, "orca_role")
                meta = {
                    "xdt_id": xdt_id, "sdk": sdk, "title": rv(r, "title", "") or "",
                    "model": rv(r, "model", "") or "", "effort": rv(r, "effort", "") or "",
                    "fast_mode": bool(rv(r, "fast_mode", False)),
                    "one_m": bool(rv(r, "one_m", False)),
                    "lifetime_real": lifetime_real,
                    "agent_kind": rv(r, "agent_kind", "cc") or "cc",
                    "source_type": classify_source_type(source, orca_role),
                    "project": basename_project(rv(r, "working_dir")),
                    "created_s": (rv(r, "created_at", 0) or 0) / 1000.0,
                    "updated_s": (rv(r, "updated_at", 0) or 0) / 1000.0,
                }
                ctx["sid_to_sdk"][xdt_id] = sdk
                if sdk:
                    ctx["meta_by_sdk"][sdk] = meta
                ctx["meta_by_sdk"].setdefault("xdtid:" + xdt_id, meta)
    except sqlite3.Error as e:
        warnings.append(f"sessions read failed: {e}")

    # Resumed/forked/cleared sessions keep their CURRENT sdk_session_id in the
    # sessions row, but transcripts on disk may use an EARLIER sdk id that only
    # survives in message agent_meta. Map those historical ids to the same XDT
    # session so their ~/.claude transcripts still attribute to XDT Maker.
    try:
        for r in con.execute("SELECT session_id, agent_meta FROM messages "
                             "WHERE agent_meta IS NOT NULL AND agent_meta != ''"):
            try:
                sdk = json.loads(r["agent_meta"]).get("sdkSessionId")
            except (ValueError, TypeError):
                continue
            if sdk and sdk not in ctx["meta_by_sdk"]:
                meta = ctx["meta_by_sdk"].get("xdtid:" + r["session_id"])
                if meta:
                    ctx["meta_by_sdk"][sdk] = meta
    except sqlite3.Error as e:
        warnings.append(f"agent_meta sdk map failed: {e}")

    try:
        ctx["sdef"] = {r["id"]: dict(r)
                       for r in con.execute("SELECT * FROM schedules")}
    except sqlite3.Error as e:
        warnings.append(f"schedules read failed: {e}")
    try:
        ctx["runs"] = [dict(r) for r in con.execute(
            "SELECT schedule_id, session_id, fired_at, status FROM "
            "schedule_runs WHERE fired_at >= ? AND fired_at <= ?",
            (cut_ms, end_ms))]
    except sqlite3.Error as e:
        warnings.append(f"schedule_runs read failed: {e}")

    con.close()
    return ctx


def read_xdt_agent_meta_fallback(ctx, cutoff_s, end_s, pricing, seen_sdk, warnings):
    """Build sessions from messages.agent_meta ONLY for XDT sessions that did not
    get a file-based transcript (e.g. codex workers, pruned jsonl). Avoids
    double-counting with the jsonl/rollout readers."""
    out = []
    db = ctx["db_path"]
    if not db:
        return out
    cut_ms, end_ms = int(cutoff_s * 1000), int(end_s * 1000)
    try:
        con = open_xdt_db(db)
    except sqlite3.Error:
        return out
    # xdt session ids whose sdk transcript was already accounted for
    covered_xdt_ids = {m["xdt_id"] for k, m in ctx["meta_by_sdk"].items()
                       if m["sdk"] in seen_sdk}
    by_sid = {}
    seen_msg = set()
    try:
        q = ("SELECT session_id, agent_meta, created_at FROM messages "
             "WHERE created_at >= ? AND created_at <= ? "
             "AND agent_meta IS NOT NULL AND agent_meta != ''")
        for r in con.execute(q, (cut_ms, end_ms)):
            xid = r["session_id"]
            if xid in covered_xdt_ids:
                continue
            meta = ctx["meta_by_sdk"].get("xdtid:" + xid)
            if meta is None:
                continue
            try:
                am = json.loads(r["agent_meta"])
            except (ValueError, TypeError):
                continue
            u = am.get("usage") or {}
            if not u:
                continue
            dk = (xid, am.get("uuid") or am.get("requestId") or r["created_at"])
            if dk in seen_msg:
                continue
            seen_msg.add(dk)
            s = by_sid.get(xid)
            if s is None:
                s = Sess("XDT Maker", meta["sdk"] or ("xdt:" + xid))
                populate_session_from_meta(s, meta)
                s.model = am.get("model") or meta["model"]
                s.model_key = model_key(s.model, pricing)
                by_sid[xid] = s
            t = {"input": u.get("inputTokens", 0) or 0,
                 "output": u.get("outputTokens", 0) or 0,
                 "cache_read": u.get("cacheReadInputTokens", 0) or 0,
                 "cache_write_5m": u.get("cacheCreationInputTokens", 0) or 0,
                 "cache_write_1h": 0}
            ts = (r["created_at"] or 0) / 1000.0
            accrue(s, t, am.get("model") or s.model, pricing, ts)
    except sqlite3.Error as e:
        warnings.append(f"agent_meta fallback failed: {e}")
    con.close()
    return list(by_sid.values())


# --------------------------------------------------------------------------- #
# Claude Code transcripts (source of truth for ALL Claude usage)              #
# --------------------------------------------------------------------------- #
def claude_project_roots():
    roots = []
    # CLAUDE_CONFIG_DIR may be comma-separated; each root already named
    # "projects" is used as-is, otherwise we append "projects".
    for part in os.environ.get("CLAUDE_CONFIG_DIR", "").split(","):
        part = part.strip()
        if not part:
            continue
        p = os.path.expanduser(part)
        roots.append(p if os.path.basename(p.rstrip("/")) == "projects"
                     else os.path.join(p, "projects"))
    roots.append(os.path.join(HOME, ".config", "claude", "projects"))
    roots.append(os.path.join(HOME, ".claude", "projects"))
    out, seen = [], set()
    for r in roots:
        rp = os.path.realpath(r)
        if rp not in seen:
            seen.add(rp)
            out.append(r)
    return out


def apply_claude_record(s, rec, pricing):
    mdl = rec["model"] or s.model
    s.model = s.model or mdl
    cost_mdl = mdl
    if rec.get("speed") == "fast" and "opus" in (mdl or "").lower():
        cost_mdl = "claude-opus-4-fast"   # fast mode = 2x premium
        s.fast_mode = True
    accrue(s, rec["t"], cost_mdl, pricing, rec["ts"])
    s.web_searches += rec["ws"]
    s.web_fetches += rec["wf"]
    if not s.project:
        s.project = basename_project(rec["cwd"])


def read_claude(ctx, cutoff_s, end_s, pricing, warnings, seen_sdk):
    sessions = []
    files = []
    seen_paths = set()
    for root in claude_project_roots():
        for fp in glob.glob(os.path.join(root, "*", "*.jsonl")):
            ap = os.path.abspath(fp)
            if ap in seen_paths:
                continue
            seen_paths.add(ap)
            files.append(ap)
    seen_session_ids = set()
    for fp in files:
        if "xdt-maker-dialogues" in fp:
            continue
        sid = os.path.splitext(os.path.basename(fp))[0]
        if sid in seen_session_ids:
            continue
        seen_session_ids.add(sid)
        meta = ctx["meta_by_sdk"].get(sid)
        s = Sess("XDT Maker" if meta else "Claude Code", sid)
        if meta:
            populate_session_from_meta(s, meta)
        else:
            s.source_type = "cli"
        touched = False
        # Claude streaming writes several assistant lines sharing one
        # (message.id, requestId) with CUMULATIVE usage; keep the last so each
        # message is counted once. Lines without an id fall back to per-line.
        keyed = {}
        try:
            with open(fp, errors="replace") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("type") != "assistant":
                        continue
                    ts = parse_ts(obj.get("timestamp"))
                    if ts is None or ts < cutoff_s or ts > end_s:
                        continue
                    msg = obj.get("message") or {}
                    u = msg.get("usage") or {}
                    if not u:
                        continue
                    cc = u.get("cache_creation") or {}
                    stu = u.get("server_tool_use") or {}
                    rec = {
                        "t": {
                            "input": u.get("input_tokens", 0) or 0,
                            "output": u.get("output_tokens", 0) or 0,
                            "cache_read": u.get("cache_read_input_tokens", 0) or 0,
                            "cache_write_5m": cc.get(
                                "ephemeral_5m_input_tokens",
                                u.get("cache_creation_input_tokens", 0)) or 0,
                            "cache_write_1h": cc.get("ephemeral_1h_input_tokens", 0) or 0,
                        },
                        "model": msg.get("model") or "",
                        "ts": ts,
                        "speed": u.get("speed"),
                        "ws": stu.get("web_search_requests", 0) or 0,
                        "wf": stu.get("web_fetch_requests", 0) or 0,
                        "cwd": obj.get("cwd"),
                    }
                    msg_id = msg.get("id")
                    if msg_id:
                        keyed[(msg_id, obj.get("requestId") or "")] = rec
                    else:
                        apply_claude_record(s, rec, pricing)
                    touched = True
        except OSError as e:
            warnings.append(f"claude {os.path.basename(fp)}: {e}")
            continue
        for rec in keyed.values():
            apply_claude_record(s, rec, pricing)
        if touched:
            if meta and meta["model"]:
                s.model = meta["model"]
            s.model_key = model_key(s.model, pricing)
            s.title = s.title or s.project or sid[:8]
            if meta:
                seen_sdk.add(sid)
            sessions.append(s)
    return sessions


# --------------------------------------------------------------------------- #
# Codex rollouts                                                               #
# --------------------------------------------------------------------------- #
def codex_session_id(pl):
    return pl.get("id") or pl.get("session_id") or pl.get("sessionId")


def codex_service_tier(config_path=None):
    """Read Codex's configured service tier from a config.toml (default
    ~/.codex/config.toml; pass a path for a nested codex-home).
    Codex 'fast' / desktop 'priority' → the expensive priority tier (~2.5x).
    Returns 'priority' | 'flex' | 'standard'. The per-request tier isn't logged
    in rollouts, so this global config is our best signal."""
    if tomllib is None:
        return "standard"
    path = config_path or os.path.join(HOME, ".codex", "config.toml")
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except (OSError, ValueError):
        return "standard"
    tiers = []
    if cfg.get("service_tier"):
        tiers.append(str(cfg["service_tier"]).lower())
    dsk = cfg.get("desktop") or {}
    if dsk.get("default-service-tier"):
        tiers.append(str(dsk["default-service-tier"]).lower())
    if any(t in ("fast", "priority") for t in tiers):
        return "priority"
    if any(t == "flex" for t in tiers):
        return "flex"
    return "standard"


def codex_priority_turns(cutoff_s, db=None):
    """Per-turn service tier from a logs_2.sqlite of websocket request logs
    (default ~/.codex/logs_2.sqlite; pass a path for a nested codex-home).
    Returns (priority_turn_ids, standard_turn_ids). Turns absent from both fall
    back to the config-level service_tier."""
    pri, std = set(), set()
    db = db or os.path.join(HOME, ".codex", "logs_2.sqlite")
    if not os.path.exists(db):
        return pri, std
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return pri, std
    marker = "websocket request:"
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(logs)")}
        if not {"ts", "feedback_log_body"} <= cols:
            return pri, std
        cut = int(cutoff_s - 2 * 86400)  # ts in epoch seconds, small slack
        for (body,) in con.execute(
                "SELECT feedback_log_body FROM logs WHERE ts >= ? AND "
                "feedback_log_body LIKE '%websocket request:%'", (cut,)):
            if not body:
                continue
            i = body.find(marker)
            if i < 0:
                continue
            try:
                req = json.loads(body[i + len(marker):].strip())
            except ValueError:
                continue
            if not isinstance(req, dict) or req.get("type") != "response.create":
                continue
            m = re.search(r'turn[._]id["\s:=]+([0-9a-f-]{8,})', body[:i])
            tid = m.group(1) if m else req.get("turn_id")
            if not tid:
                continue
            st = req.get("service_tier")
            if st == "priority":
                pri.add(tid)
            elif st in ("default", "standard", "flex", "auto"):
                std.add(tid)
    except sqlite3.Error:
        pass
    finally:
        con.close()
    return pri, std


def codex_roots(ctx):
    """Codex home dirs to scan: $CODEX_HOME, ~/.codex, and the XDT-managed
    codex-home alongside the XDT DB (where XDT's codex workers write)."""
    roots = []
    env = os.environ.get("CODEX_HOME", "").strip()
    if env:
        roots.append(os.path.expanduser(env))
    roots.append(os.path.join(HOME, ".codex"))
    if ctx.get("db_path"):
        roots.append(os.path.join(os.path.dirname(ctx["db_path"]), "codex-home"))
    out, seen = [], set()
    for r in roots:
        rp = os.path.realpath(r)
        if rp not in seen and os.path.isdir(rp):
            seen.add(rp)
            out.append(r)
    return out


def _parse_codex_file(fp, ctx, cutoff_s, end_s, pricing, warnings,
                      tier, pri_ids, std_ids, source_name="Codex", enrich_xdt=True):
    """Parse one Codex rollout file into a Sess (or None). Shared by the built-in
    Codex reader and any tool that nests standard codex-homes (e.g. OpenClaw)."""
    s = Sess(source_name, os.path.basename(fp))
    s.source_type = "codex"
    cur_model = ""
    cur_turn_id = None
    meta = None
    touched = False
    title_txt = ""
    # Built-in Codex titles come from XDT metadata; only tools that nest codex
    # (enrich_xdt=False, e.g. OpenClaw) need a title scraped from the first real
    # user message — otherwise every session's title degrades to its cwd.
    want_title = not enrich_xdt
    try:
        with open(fp, errors="replace") as f:
            for line in f:
                is_core = ('"session_meta"' in line or '"turn_context"' in line
                           or '"token_count"' in line)
                is_user = (want_title and not title_txt
                           and ('"role":"user"' in line or '"role": "user"' in line
                                or '"user_message"' in line))
                if not is_core and not is_user:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if is_user and not title_txt:
                    cand = _openclaw_clean_title(_codex_user_text(obj))
                    if cand:
                        title_txt = cand[:80]
                    if not is_core:
                        continue
                typ, pl = obj.get("type"), obj.get("payload") or {}
                if typ == "session_meta":
                    s.id = codex_session_id(pl) or s.id
                    s.project = basename_project(pl.get("cwd"))
                    cur_model = cur_model or pl.get("model") or ""
                    if enrich_xdt and ctx is not None:
                        meta = ctx["meta_by_sdk"].get(s.id)
                        # Host = where it actually ran (rollout originator). XDT
                        # Maker only *indexes* standalone Codex Desktop/CLI
                        # sessions into its DB — that does NOT make XDT the host.
                        # Only genuinely XDT-orchestrated codex (orca worker/lead)
                        # counts as XDT Maker.
                        if meta and meta["source_type"] in ("worker", "orca-lead"):
                            s.source = "XDT Maker"
                            s.source_type = meta["source_type"]
                            s.title = meta["title"]
                        elif meta:
                            s.title = meta["title"] or s.title
                elif typ == "turn_context":
                    cur_model = pl.get("model") or cur_model
                    cur_turn_id = pl.get("turn_id") or cur_turn_id
                    s.effort = pl.get("effort") or s.effort
                elif typ == "event_msg" and pl.get("type") == "token_count":
                    ts = parse_ts(obj.get("timestamp"))
                    if ts is None or ts < cutoff_s or ts > end_s:
                        continue
                    ltu = (pl.get("info") or {}).get("last_token_usage") or {}
                    if not ltu:
                        continue
                    inp = ltu.get("input_tokens", 0) or 0
                    cached = ltu.get("cached_input_tokens", 0) or 0
                    out = ltu.get("output_tokens", 0) or 0
                    s.reasoning_output += ltu.get("reasoning_output_tokens", 0) or 0
                    t = {"input": max(inp - cached, 0), "output": out,
                         "cache_read": cached, "cache_write_5m": 0,
                         "cache_write_1h": 0}
                    # per-turn tier: explicit from logs, else config fallback
                    if cur_turn_id in pri_ids:
                        is_pri = True
                    elif cur_turn_id in std_ids:
                        is_pri = False
                    else:
                        is_pri = (tier == "priority")
                    if is_pri:
                        cmodel = "gpt-5.x-priority"
                        s.fast_mode = True
                    elif inp > 272_000:
                        cmodel = "gpt-5.x-above272k"   # >272k input = 2x/1.5x
                    else:
                        cmodel = cur_model or "gpt-5.5"
                    accrue(s, t, cmodel, pricing, ts)
                    touched = True
    except OSError as e:
        warnings.append(f"codex {os.path.basename(fp)}: {e}")
        return None
    if not touched:
        return None
    s.model = (meta["model"] if meta and meta["model"] else cur_model) or "gpt-5.5"
    s.model_key = model_key(s.model, pricing)
    s.title = s.title or title_txt or s.project or s.id[:8]
    return s


def _openclaw_clean_title(msg):
    """OpenClaw prepends a large injected context blob to each user turn (skills
    catalog, project/user/telegram metadata in fenced ```json blocks); the REAL
    user request trails the last fenced block. Return that tail as a title, or ""
    if there's no genuine ask (autonomous/heartbeat turns) → caller falls back."""
    msg = (msg or "").strip()
    if not msg:
        return ""
    if msg.startswith(("OpenClaw", "Conversation info", "Conversation context")):
        # strip the injected context: the ask follows the last ``` fence
        if "```" in msg:
            msg = msg.rsplit("```", 1)[-1].strip()
        else:
            return ""
    if not msg or msg.startswith(("<", "OpenClaw", "Conversation")):
        return ""
    return " ".join(msg.split())


def _codex_user_text(o):
    """First readable user text from a Codex rollout `response_item`
    (role=user → content blocks) or an `event_msg` user message."""
    if o.get("role") == "user":
        c = o.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict):
                    t = b.get("text") or b.get("content")
                    if isinstance(t, str) and t.strip():
                        return t
                elif isinstance(b, str) and b.strip():
                    return b
    pl = o.get("payload") or {}
    if pl.get("type") in ("user_message", "user_instructions"):
        m = pl.get("message") or pl.get("text")
        if isinstance(m, str):
            return m
    return ""


def _codex_files(homes):
    """{abs_path: is_archived} for sessions/ + archived_sessions/ under homes."""
    files = {}
    for home in homes:
        for sub, is_archived in (("sessions", False), ("archived_sessions", True)):
            base = os.path.join(home, sub)
            for fp in glob.glob(os.path.join(base, "**", "*.jsonl"), recursive=True):
                files.setdefault(os.path.abspath(fp), is_archived)
    return files


def read_codex(ctx, cutoff_s, end_s, pricing, warnings):
    sessions = []
    tier = codex_service_tier()
    pri_ids, std_ids = codex_priority_turns(cutoff_s)
    if pri_ids or std_ids:
        warnings.append(f"Codex 服务档逐 turn 判定(logs_2.sqlite):{len(pri_ids)} "
                        f"priority / {len(std_ids)} standard turn;未记录的 turn 回退 "
                        f"config(service_tier={tier})。priority 按 2.5× 计价。")
    elif tier == "priority":
        warnings.append("Codex 无 logs_2.sqlite 逐 turn 数据 → 按 config "
                        "service_tier=fast/priority 全算 priority(≈2.5×;缓存价估算)。")
    mtime_slack = (end_s - cutoff_s) + 86400
    seen_ids = set()
    for fp, is_archived in sorted(_codex_files(codex_roots(ctx)).items()):
        try:
            if not is_archived and os.path.getmtime(fp) < cutoff_s - mtime_slack:
                continue
        except OSError:
            continue
        s = _parse_codex_file(fp, ctx, cutoff_s, end_s, pricing, warnings,
                              tier, pri_ids, std_ids, "Codex", True)
        if s is None or s.id in seen_ids:
            continue
        seen_ids.add(s.id)
        sessions.append(s)
    return sessions


# --------------------------------------------------------------------------- #
# Schedules: cost from deduped session estimates                              #
# --------------------------------------------------------------------------- #
def apply_schedule_metadata(ctx, sessions):
    scheduled = {}
    for run in ctx["runs"]:
        sdk = ctx["sid_to_sdk"].get(run["session_id"])
        if sdk:
            scheduled.setdefault(sdk, run["schedule_id"])
    for s in sessions:
        sid = scheduled.get(s.id)
        if not sid:
            if s.source_type == "scheduler" and not s.schedule_name:
                s.schedule_name = infer_schedule_name(s.title)
            continue
        d = ctx["sdef"].get(sid, {})
        s.source_type = "scheduler"
        s.schedule_id = sid
        s.schedule_name = d.get("name") or sid


def model_label(s):
    return " ".join(x for x in (s.model, s.effort) if x)


def infer_schedule_name(title):
    fallback = "未关联 schedule_runs 的定时任务"
    if title and title.startswith("[Schedule]"):
        return title[len("[Schedule]"):].strip() or fallback
    return fallback


def build_schedule_report(ctx, sess_by_sdk, sessions):
    agg = defaultdict(lambda: {"runs": 0, "errors": 0, "cost": 0.0, "name": "",
                               "model": "", "cron": "", "sdks": set(),
                               "models": defaultdict(int)})
    costed = set()  # cost each session once across all schedules
    for run in ctx["runs"]:
        d = ctx["sdef"].get(run["schedule_id"], {})
        a = agg[run["schedule_id"]]
        a["runs"] += 1
        a["name"] = d.get("name") or run["schedule_id"]
        a["model"] = d.get("model") or ""
        a["cron"] = d.get("cron_expr") or ""
        st = run.get("status")
        if st and st not in ("success", "ok", "done", "completed"):
            a["errors"] += 1
        sdk = ctx["sid_to_sdk"].get(run["session_id"])
        if sdk and sdk not in a["sdks"]:
            a["sdks"].add(sdk)
            s = sess_by_sdk.get(sdk)
            if s and sdk not in costed:
                costed.add(sdk)
                a["cost"] += s.cost
                model = model_label(s)
                if model:
                    a["models"][model] += 1
    # Scheduler sessions not linked via schedule_runs in-window: fold into the
    # matching named schedule if one exists, else an inferred bucket.
    name_to_key = {a["name"]: k for k, a in agg.items()}
    for s in sessions:
        if s.source_type != "scheduler" or s.schedule_id or s.id in costed:
            continue
        costed.add(s.id)
        name = s.schedule_name or infer_schedule_name(s.title)
        key = name_to_key.setdefault(name, "inferred:" + name)
        a = agg[key]
        a["runs"] += 1
        a["name"] = name
        a["cost"] += s.cost
        model = model_label(s)
        if model:
            a["models"][model] += 1
    for a in agg.values():
        if not a["model"] and a["models"]:
            a["model"] = sorted(a["models"].items(), key=lambda kv: kv[1], reverse=True)[0][0]
        a.pop("sdks", None)
        a.pop("models", None)
    return dict(agg)


# --------------------------------------------------------------------------- #
# Waste detection                                                             #
# --------------------------------------------------------------------------- #
def detect_waste(sessions, cfg):
    flags = defaultdict(list)
    costs = sorted((s.cost for s in sessions if s.cost > 0), reverse=True)
    median_cost = costs[len(costs) // 2] if costs else 0.0
    for s in sessions:
        if (s.turns > 1 and s.cost >= cfg["low_cache_min_cost"]
                and billable_input(s.tok) > 50_000):
            if cache_ratio(s.tok) < cfg["low_cache_ratio"]:
                s.flags.append(f"low-cache({cache_ratio(s.tok):.0%})")
                flags["low_cache"].append(s)
        premium = s.model_key in ("claude-opus-4", "gpt-5.5", "gpt-5", "gpt-5-codex")
        if (premium and 0 < s.tok["output"] < cfg["small_output"]
                and s.turns <= cfg["small_turns"] and s.cost < cfg["small_cost"]
                and s.effort.lower() in ("high", "xhigh")):
            s.flags.append("premium-on-small")
            flags["downgrade"].append(s)
        if (median_cost > 0 and s.cost > median_cost * cfg["runaway_mult"]
                and s.cost >= cfg["runaway_min_cost"]):
            s.flags.append("expensive-outlier")
            flags["runaway"].append(s)
    return flags, median_cost


# --------------------------------------------------------------------------- #
# Rendering                                                                    #
# --------------------------------------------------------------------------- #
def fmt_usd(x):
    return f"${x:,.2f}"


def fmt_tok(n):
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.1f}M"
    if n >= 1e3:
        return f"{n/1e3:.0f}k"
    return str(int(n))


def group_sum(sessions, keyfn):
    agg = defaultdict(lambda: {"cost": 0.0, "tok_in": 0, "tok_out": 0,
                               "cache_read": 0, "n": 0, "tok_all": 0})
    for s in sessions:
        a = agg[keyfn(s)]
        a["cost"] += s.cost
        a["tok_in"] += billable_input(s.tok)
        a["tok_out"] += s.tok["output"]
        a["cache_read"] += s.tok["cache_read"]
        a["tok_all"] += total_tokens(s.tok)
        a["n"] += 1
    return agg


ST_LABEL = {"scheduler": "定时任务", "desktop": "桌面交互", "feishu": "飞书",
            "worker": "Orca worker", "orca-lead": "Orca lead",
            "cli": "命令行", "codex": "Codex"}


def st_label(x):
    return ST_LABEL.get(x, x or "?")


def flag_zh(f):
    if f.startswith("low-cache"):
        return f.replace("low-cache", "低缓存")
    return {"expensive-outlier": "花费偏高", "premium-on-small": "大材小用",
            "1M-context": "1M上下文"}.get(f, f)


def flags_zh(flags):
    return ",".join(flag_zh(x) for x in flags) or "-"


def model_family(m):
    m = (m or "").lower()
    if "opus" in m:
        return "Claude opus"
    if "sonnet" in m:
        return "Claude sonnet"
    if "haiku" in m:
        return "Claude haiku"
    if "gpt-5" in m or "codex" in m:
        return "Codex/gpt-5.x"
    return m or "?"


def billing_of(model, billing):
    """metered (real pay-per-token $) vs subscription (flat fee, marginal ~$0)."""
    m = (model or "").lower()
    if any(k in m for k in ("opus", "sonnet", "haiku", "claude")):
        return billing.get("claude", "metered")
    if "gpt-5" in m or "codex" in m:
        return billing.get("codex", "subscription")
    return billing.get("default", "metered")


def sess_billing(s, billing):
    """Billing mode for a session: explicit per-session override (set by tools
    whose billing is a property of the tool, e.g. Pi's own plan) wins; otherwise
    derive from the model family."""
    return s.billing or billing_of(s.model, billing)


def billing_tag(mode):
    return {"metered": "按量·真金", "subscription": "包月·$0边际"}.get(mode, mode)


def pct_table(agg, total, label, top=None):
    rows = sorted(agg.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    tail = []
    if top and len(rows) > top:
        tail = rows[top:]
        rows = rows[:top]
    out = [f"| {label} | 折算$ | 占比 | session数 | tokens | 缓存复用率 |",
           "|---|--:|--:|--:|--:|--:|"]
    for k, a in rows:
        p = (a["cost"] / total * 100) if total else 0
        ch = (a["cache_read"] / a["tok_in"] * 100) if a["tok_in"] else 0
        out.append(f"| {k} | {fmt_usd(a['cost'])} | {p:.0f}% | {a['n']} | "
                   f"{fmt_tok(a['tok_all'])} | {ch:.0f}% |")
    if tail:
        c = sum(a["cost"] for _, a in tail)
        n = sum(a["n"] for _, a in tail)
        ta = sum(a["tok_all"] for _, a in tail)
        p = (c / total * 100) if total else 0
        out.append(f"| _(其余 {len(tail)} 项)_ | {fmt_usd(c)} | {p:.0f}% | {n} | "
                   f"{fmt_tok(ta)} | |")
    return "\n".join(out)


def render(sessions, ctx, sched, flags, median_cost, cfg, warnings):
    L, win = [], cfg["window_label"]
    total = sum(s.cost for s in sessions)
    daily = ctx["daily_real"]
    bill = cfg.get("billing", {})
    by_source = group_sum(sessions, lambda s: s.source)

    L += [f"# AI 耗量审计 — {win}", "",
          f"_生成于 {cfg['now_str']}。**花费 = token 用量 × 公开 API 标价**"
          f"(pricing.json {cfg.get('pricing_version','?')})。**计费混合**:Claude/XDT "
          f"按量 API → 美元=真金白银;Codex 等包月订阅 → 美元=what-if(边际≈$0,不是现金)。"
          f"价格可能过时,跑前建议联网复核。_", ""]
    L += ["## 总览", "",
          f"- **折算花费(按 API 标价等价):{fmt_usd(total)}**,{win},"
          f"共 {len(sessions)} 个 session"]
    for src, a in sorted(by_source.items(), key=lambda kv: -kv[1]["cost"]):
        L.append(f"  - {src}:{fmt_usd(a['cost'])} "
                 f"({a['cost']/total*100 if total else 0:.0f}%),"
                 f"{a['n']} 个 session,{fmt_tok(a['tok_all'])} tokens")
    if daily:
        L.append(f"- _XDT `daily_spend` = Claude 按量**实际花掉的现金**(权威口径):"
                 f"窗口内 **{fmt_usd(sum(daily.values()))}**(详见下方 ledger 表)。_")
    _byfam = group_sum(sessions, lambda s: model_family(s.model))
    _ftok = sum(a["tok_all"] for a in _byfam.values()) or 1
    real_cash = sum(s.cost for s in sessions
                    if sess_billing(s, bill) == "metered")
    whatif = sum(s.cost for s in sessions
                 if sess_billing(s, bill) == "subscription")
    L.append(f"- **真金白银(按量 API,主要是 Claude):≈{fmt_usd(real_cash)}** · "
             f"包月渠道(Codex 等)API-等价 what-if {fmt_usd(whatif)}"
             f"(订阅,边际≈$0,不是现金)")
    # When ≥2 host Apps each draw on a subscription (codex/gpt-5.x) backend, their
    # what-if dollars share ONE flat fee — they are NOT additive cash. Surface it
    # so two big what-if numbers aren't misread as stacked real spend.
    sub_by_src = defaultdict(float)
    for s in sessions:
        if sess_billing(s, bill) == "subscription":
            sub_by_src[s.source] += s.cost
    sub_srcs = sorted(((k, v) for k, v in sub_by_src.items() if v > 0),
                      key=lambda kv: -kv[1])
    if len(sub_srcs) >= 2:
        L.append("  - ⚠️ _" + "、".join(f"{k} {fmt_usd(v)}" for k, v in sub_srcs)
                 + " 都跑在**包月订阅后端**(codex/gpt-5.x,边际 $0)。这些 what-if 美元"
                 "**不叠加成真金**——真金只是那一份月费;它们反映的是**配额 / token 消耗"
                 "的分布**,不是各自又花掉这么多现金。_")
    L.append("- 按模型族 · 美元: " + " · ".join(
        f"{k}[{billing_tag(billing_of(k, bill))}] {fmt_usd(a['cost'])}"
        f"({a['cost']/total*100 if total else 0:.0f}%)"
        for k, a in sorted(_byfam.items(), key=lambda kv: -kv[1]["cost"])))
    L.append("- 按模型族 · token: " + " · ".join(
        f"{k} {fmt_tok(a['tok_all'])}({a['tok_all']/_ftok*100:.0f}%)"
        for k, a in sorted(_byfam.items(), key=lambda kv: -kv[1]["tok_all"])))
    L.append("")

    L += ["## 按来源(宿主 App)", "", pct_table(by_source, total, "来源"), ""]

    if daily:
        L += ["## XDT Maker 真实现金 ledger(Claude 按量,与窗口相交的账单日)", "",
              "| 日期 | 花费 |", "|---|--:|"]
        L += [f"| {d} | {fmt_usd(daily[d])} |" for d in sorted(daily, reverse=True)]
        L.append("")
        L.append(f"_这是 Claude/XDT 按量计费**实际花掉的现金**(对照上面 real-cash 估算 "
                 f"≈{fmt_usd(real_cash)},因 agent_meta 覆盖率 / 窗口边界 / 计价口径"
                 f"略有差异)。Codex 包月不进此账。session 用滚动 24h 窗口、ledger 按"
                 f"自然日,故可能含边界相交日。_")
        L.append("")

    L += ["## 按模型", "",
          pct_table(group_sum(sessions, lambda s: s.model or "(未知)"),
                    total, "模型"), ""]
    L += ["## 按 来源 × 模型族(宿主 App × 模型,两维一起看)", "",
          pct_table(group_sum(
              sessions, lambda s: f"{s.source} · {model_family(s.model)}"),
              total, "来源 × 模型"), ""]
    L += ["## 按使用类型", "",
          pct_table(group_sum(sessions, lambda s: st_label(s.source_type)),
                    total, "类型"), ""]
    # Projectless buckets (dialogue chats etc.) stay collapsed when small, but an
    # individually expensive one is broken out by its title so it isn't hidden.
    collapsed = {"(XDT 对话·无代码项目)", "(slock agent·无代码项目)",
                 "(无项目)", "(none)", "(无)"}
    brk = cfg.get("dialogue_breakout_cost", 2.0)

    def proj_key(s):
        p = s.project or "(无)"
        if p in collapsed and s.cost >= brk:
            return "对话:" + ((s.title or "").strip()[:24] or s.id[:8])
        return p

    L += ["## 按项目(工作目录)", "",
          pct_table(group_sum(sessions, proj_key), total, "项目", top=cfg["top"]),
          "", f"_无代码项目的对话默认合并;单个 ≥{fmt_usd(brk)} 的按标题单列。_", ""]

    L += [f"## 最贵的 {cfg['top']} 个 session", "",
          "_「项目」来自 session 的实际工作目录(cwd),是\"干了啥\"的可靠信号;"
          "「标题」是会话第一句话/外部元数据,resume 续用的老会话可能过时(标题归 A、"
          "实际在做 B),两者不一致时以项目为准。_", "",
          "| 折算$ | 来源 | 模型 | 类型 | turns | tokens | 缓存复用 | 标记 | 项目 | 标题 |",
          "|--:|---|---|---|--:|--:|--:|---|---|---|"]
    for s in sorted(sessions, key=lambda x: x.cost, reverse=True)[:cfg["top"]]:
        ttl = (s.title or "")[:34].replace("|", "/").replace("\n", " ")
        proj = (s.project or "")[:20].replace("|", "/")
        L.append(f"| {fmt_usd(s.cost)} | {s.source} | {s.model} | "
                 f"{st_label(s.source_type)} | {s.turns} | "
                 f"{fmt_tok(total_tokens(s.tok))} | {cache_ratio(s.tok)*100:.0f}% "
                 f"| {flags_zh(s.flags)} | {proj} | {ttl} |")
    L.append("")

    if sched:
        L += ["## 定时 / 周期任务", "",
              "| 任务 | 运行次数 | 失败 | 折算花费 | 模型 | cron |",
              "|---|--:|--:|--:|---|---|"]
        for _, a in sorted(sched.items(), key=lambda kv: kv[1]["cost"],
                           reverse=True):
            L.append(f"| {a['name'][:36]} | {a['runs']} | {a['errors']} | "
                     f"{fmt_usd(a['cost'])} | {a['model']} | {a['cron']} |")
        L.append("")

    L += ["## 思考深度(effort)与快速模式", ""]
    L.append(pct_table(group_sum(
        sessions, lambda s: f"{model_family(s.model)} · effort={s.effort or '默认'}"),
        total, "模型族 · effort"))
    L.append("")
    fast = [s for s in sessions if s.fast_mode]
    if fast:
        L.append(f"- **快速模式:{len(fast)} 个 session 命中 fast/priority,合计 "
                 f"{fmt_usd(sum(s.cost for s in fast))}(已按溢价计价)。** "
                 f"按量渠道是真金白银、确认是否值得;包月渠道多烧配额。")
    else:
        L.append("- **快速模式:未使用 ✓** —— 没在烧 fast 溢价。"
                 "(提醒:Opus fast = 2×($30/$150);Codex priority ≈ 2.5×"
                 "($12.5/$75),按需才开。)")
    cdx_x = [s for s in sessions if model_family(s.model).startswith("Codex")
             and (s.effort or "").lower() == "xhigh"]
    if cdx_x:
        L.append(f"- **Codex 思考深度:{len(cdx_x)} 个 session 顶格 xhigh**。Codex 包月"
                 f"($0 边际),钱上无影响,但 xhigh 多烧 reasoning token + 更慢 —— "
                 f"日常 / 简单任务降到 high/medium 省配额和时间。")
    cc_x = [s for s in sessions if model_family(s.model).startswith("Claude")
            and (s.effort or "").lower() == "xhigh"]
    if cc_x:
        L.append(f"- **Claude xhigh:{len(cc_x)} 个 session**(按量·真金,reasoning 越深 "
                 f"output 越多 = 越贵)。确认是否真需要 xhigh,否则用 high。")
    L.append("")

    L += ["## 浪费与优化信号", "",
          f"_(session 花费中位数:{fmt_usd(median_cost)};只单列值得人工看的——按量真金 "
          f"≥{fmt_usd(cfg['waste_list_min'])} 或 包月 ≥{fmt_usd(cfg['waste_sub_list_min'])},"
          f"其余只给汇总。)_",
          "_口径:**按量(Claude/XDT)= 真金,优先省**;**包月(Codex 等)边际 $0**,"
          "只清死循环 / 遗留 cron / 重复重缓存(省的是配额与时间,不是钱)。_", ""]

    def _metered(s):
        return sess_billing(s, bill) == "metered"

    def _sum(items):
        return sum(s.cost for s in items)

    # 大材小用:聚合成一行,不再逐条堆几百个 $0.x 的小活。
    dn = flags.get("downgrade", [])
    if dn:
        dm = [s for s in dn if _metered(s)]
        line = (f"- **大材小用(高级模型干小活):** {len(dn)} 个、合计 {fmt_usd(_sum(dn))}。")
        if _sum(dm) >= cfg["waste_list_min"]:
            line += (f" 其中**按量真金 {len(dm)} 个 = {fmt_usd(_sum(dm))}**,值得换 "
                     f"Sonnet/Haiku 或降 effort;其余为包月($0,省配额)。")
        else:
            line += " 基本都是包月($0 边际),省的是配额/时间,不是钱;不必逐个处理。"
        L.append(line)
        agg = defaultdict(lambda: [0, 0.0])
        for s in dn:
            k = s.schedule_name or s.project or "(其它)"
            agg[k][0] += 1
            agg[k][1] += s.cost
        top = sorted(agg.items(), key=lambda kv: -kv[1][1])[:3]
        if top:
            L.append("  - 主要来自:" + "、".join(
                f"`{k}` {n} 次 / {fmt_usd(c)}" for k, (n, c) in top))

    # 花费偏高:汇总一行(真金 / 包月分开),明细在下方按"值得看"过滤。
    rn = flags.get("runaway", [])
    if rn:
        rm = [s for s in rn if _metered(s)]
        rs = [s for s in rn if not _metered(s)]
        L.append(f"- **花费偏高(>中位数 {cfg['runaway_mult']:.0f} 倍):** {len(rn)} 个 —— "
                 f"按量真金 {fmt_usd(_sum(rm))} / 包月 what-if {fmt_usd(_sum(rs))}。"
                 f"真金的逐个看是否值;包月的只排死循环 / 跑飞自动化。")
    L.append("")

    def worth(s):
        floor = cfg["waste_list_min"] if _metered(s) else cfg["waste_sub_list_min"]
        return s.cost >= floor

    def dump(kind, title, fmt):
        items = sorted((s for s in flags.get(kind, []) if worth(s)),
                       key=lambda x: x.cost, reverse=True)
        if not items:
            return
        shown = items[:cfg["waste_list_top"]]
        L.append(f"### {title}")
        L.append("")
        for s in shown:
            L.append(f"- [{billing_tag(sess_billing(s, bill))}] " + fmt(s))
        if len(items) > len(shown):
            L.append(f"- _…其余 {len(items) - len(shown)} 项从略_")
        L.append("")

    dump("runaway", "花费偏高 session(值得单看)",
         lambda s: f"{fmt_usd(s.cost)} —— {s.source}/{st_label(s.source_type)} "
                   f"`{s.model}` {s.turns} turns,{s.duration_min:.0f} 分钟 —— "
                   f"{(s.title or '')[:50]}")
    dump("low_cache", "缓存复用率低(不是严格 hit rate;已排除首轮建 cache)",
         lambda s: f"{fmt_usd(s.cost)} —— 缓存复用率 {cache_ratio(s.tok):.0%},"
                   f"{fmt_tok(billable_input(s.tok))} input tok `{s.model}` —— "
                   f"{(s.title or '')[:50]}")
    cov = cfg.get("coverage") or []
    if cov:
        L += ["## 覆盖范围(本机探测的工具)", "",
              "_本 skill 检查了下列写本地 token 日志的工具。「已装·窗口内无数据」= 工具在"
              "但这段时间没用;「未安装」= 本机未发现其数据。这样你能看到**查了哪些**,"
              "而不只是查到了什么。_", "",
              "| 工具 | 状态 | 计费 | 说明 |", "|---|---|---|---|"]
        order = {"有数据": 0, "已装·窗口内无数据": 1, "未安装": 2, "未启用": 3}
        for r in sorted(cov, key=lambda x: (order.get(x["status"], 9), x["name"])):
            vmark = ("(未核实格式)" if r["verified"] is False
                     and r["status"] not in ("未安装", "未启用") else "")
            bt = billing_tag(r["billing"]) if r["billing"] else ""
            L.append(f"| {r['name']}{vmark} | {r['status']} | {bt} | {r['detail']} |")
        L.append("")
    if warnings:
        L += ["## 警告", ""] + [f"- {w}" for w in warnings] + [""]
    return "\n".join(L)


def to_json(sessions, ctx, sched, flags, cfg, warnings):
    def sd(s):
        return {"source": s.source, "id": s.id, "title": s.title,
                "model": s.model, "source_type": s.source_type,
                "project": s.project, "turns": s.turns,
                "est_cost": round(s.est_cost, 4),
                "lifetime_real": (round(s.lifetime_real, 4)
                                  if s.lifetime_real is not None else None),
                "tokens": s.tok, "cache_ratio": round(cache_ratio(s.tok), 4),
                "billing": sess_billing(s, cfg.get("billing", {})),
                "one_m": s.one_m, "effort": s.effort, "fast_mode": s.fast_mode,
                "web_searches": s.web_searches, "web_fetches": s.web_fetches,
                "reasoning_output": s.reasoning_output,
                "schedule_id": s.schedule_id or None,
                "schedule_name": s.schedule_name or None,
                "duration_min": round(s.duration_min, 1), "flags": s.flags}
    return {"window": cfg["window_label"], "generated": cfg["now_str"],
            "xdt_db_path": ctx["db_path"],
            "warnings": warnings,
            "total_est": round(sum(s.cost for s in sessions), 2),
            "real_cash_est": round(sum(
                s.cost for s in sessions
                if sess_billing(s, cfg.get("billing", {})) == "metered"), 2),
            "whatif_est": round(sum(
                s.cost for s in sessions
                if sess_billing(s, cfg.get("billing", {})) == "subscription"), 2),
            "xdt_ledger_real": round(sum(ctx["daily_real"].values()), 2),
            "daily_real": ctx["daily_real"],
            "schedules": {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv)
                              for kk, vv in v.items()}
                          for k, v in sched.items()},
            "flag_counts": {k: len(v) for k, v in flags.items()},
            "coverage": cfg.get("coverage"),
            "sessions": [sd(s) for s in sorted(sessions, key=lambda x: x.cost,
                                               reverse=True)]}


# --------------------------------------------------------------------------- #
# Generic config-driven providers (providers.json)                            #
# --------------------------------------------------------------------------- #
def get_path(obj, dotted, default=None):
    cur = obj
    for part in (dotted or "").split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def get_first(obj, spec, default=None):
    """Like get_path but `spec` may be a single dotted path OR a list of dotted
    paths (first one that resolves to a non-None value wins). Lets a config field
    map list provider aliases, e.g. ['usage.input', 'usage.input_tokens']."""
    if isinstance(spec, (list, tuple)):
        for p in spec:
            v = get_path(obj, p)
            if v is not None:
                return v
        return default
    v = get_path(obj, spec, default)
    return default if v is None else v


def parse_epoch_or_iso(v):
    """Pi-style timestamp: epoch seconds, epoch ms (>1e12), or ISO string."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0 if v > 1e12 else float(v)
    if isinstance(v, str):
        s = v.strip()
        if s.replace(".", "", 1).isdigit():
            n = float(s)
            return n / 1000.0 if n > 1e12 else n
        return parse_ts(s)
    return None


def expand_roots(roots):
    """Resolve [{env, path, glob}] → [(base_dir, glob)], env overrides path."""
    out, seen = [], set()
    for r in roots or []:
        base = (os.environ.get(r["env"]) if r.get("env") else None) or r.get("path", "")
        if not base:
            continue
        base = os.path.expanduser(base)
        rp = os.path.realpath(base)
        if rp not in seen:
            seen.add(rp)
            out.append((base, r.get("glob", "**/*.jsonl")))
    return out


def load_providers(path):
    try:
        with open(path) as f:
            return json.load(f).get("providers", [])
    except (OSError, json.JSONDecodeError):
        return []


def read_generic_jsonl(prov, cutoff_s, end_s, pricing, warnings):
    """Config-driven adapter for any tool that writes per-message token usage to
    JSONL. `fields` uses dotted paths (e.g. 'message.usage.input_tokens'). One
    Sess per file; windowed by per-line `ts` if mapped, else by file mtime.
    Graceful no-op if the tool's roots don't exist (tool not installed)."""
    fmap = prov.get("fields") or {}
    if not (fmap.get("input") or fmap.get("output")):
        return []
    files, seen = [], set()
    for base, gl in expand_roots(prov.get("roots")):
        if not os.path.isdir(base):
            continue
        for fp in glob.glob(os.path.join(base, gl), recursive=True):
            ap = os.path.abspath(fp)
            if ap not in seen:
                seen.add(ap)
                files.append(ap)
    name = prov.get("name", "provider")
    st = prov.get("source_type", "cli")
    pbilling = prov.get("billing", "")
    type_key, type_val = fmap.get("type_key"), fmap.get("type_value")
    has_ts = bool(fmap.get("ts"))
    sessions = []
    for fp in files:
        try:
            fmtime = os.path.getmtime(fp)
        except OSError:
            continue
        if not has_ts and fmtime < cutoff_s:
            continue
        s = Sess(name, os.path.splitext(os.path.basename(fp))[0])
        s.source_type = st
        s.billing = pbilling
        s.project = basename_project(os.path.dirname(fp))
        touched = False
        try:
            with open(fp, errors="replace") as f:
                for line in f:
                    if "{" not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    if type_key and get_path(o, type_key) != type_val:
                        continue
                    ts = parse_epoch_or_iso(get_first(o, fmap["ts"])) if has_ts else fmtime
                    if ts is None or ts < cutoff_s or ts > end_s:
                        continue
                    inp = get_first(o, fmap.get("input", ""), 0) or 0
                    out = get_first(o, fmap.get("output", ""), 0) or 0
                    if not inp and not out:
                        continue
                    cr = get_first(o, fmap.get("cache_read", ""), 0) or 0
                    if fmap.get("cached_in_input"):
                        inp = max(inp - cr, 0)   # provider's input already incl cache
                    t = {"input": inp, "output": out, "cache_read": cr,
                         "cache_write_5m": get_first(o, fmap.get("cache_write", ""), 0) or 0,
                         "cache_write_1h": 0}
                    mdl = get_first(o, fmap.get("model", ""), "") or prov.get("model", "")
                    s.model = s.model or mdl
                    accrue(s, t, mdl or s.model, pricing, ts)
                    touched = True
        except OSError as e:
            warnings.append(f"{name} {os.path.basename(fp)}: {e}")
            continue
        if touched:
            s.model_key = model_key(s.model, pricing)
            s.title = s.title or s.project or s.id[:8]
            sessions.append(s)
    return sessions


# Provider strings Pi attaches to a message/model_change → our pricing family.
# Mirrors CodexBar PiSessionCostScanner: only openai-codex & anthropic are
# costed; any other provider tag means the row is dropped (we can't price it).
PI_PROVIDER_MAP = {"openai-codex": "codex", "anthropic": "claude",
                   "openai": "codex"}
PI_USAGE = {
    "input": ["usage.input", "usage.inputTokens", "usage.input_tokens",
              "usage.promptTokens", "usage.prompt_tokens"],
    "cache_read": ["usage.cacheRead", "usage.cacheReadTokens", "usage.cache_read",
                   "usage.cache_read_tokens", "usage.cacheReadInputTokens",
                   "usage.cache_read_input_tokens"],
    "cache_write": ["usage.cacheWrite", "usage.cacheWriteTokens", "usage.cache_write",
                    "usage.cache_write_tokens", "usage.cacheCreationTokens",
                    "usage.cache_creation_tokens", "usage.cacheCreationInputTokens",
                    "usage.cache_creation_input_tokens"],
    "output": ["usage.output", "usage.outputTokens", "usage.output_tokens",
               "usage.completionTokens", "usage.completion_tokens"],
}


def read_pi(prov, cutoff_s, end_s, pricing, warnings):
    """Pi (~/.pi/agent/sessions/**/*.jsonl). Faithful port of CodexBar's
    PiSessionCostScanner: a `model_change` line sets the current (provider, model)
    context; each assistant `message` line carries `message.usage`. Pi proxies
    upstream models, so we price by the upstream FAMILY (openai-codex→gpt-5.x,
    anthropic→claude) and route cache tokens the same way each upstream bills:
    Codex folds cache-write into input (no separate write rate); Anthropic prices
    cache-write separately. Rows whose provider tag is present but unknown are
    dropped (we won't guess a price). Pi's own plan is the billing basis."""
    fmap = prov.get("fields") or {}
    pbilling = prov.get("billing", "subscription")
    files, seen = [], set()
    for base, gl in expand_roots(prov.get("roots")):
        if not os.path.isdir(base):
            continue
        for fp in glob.glob(os.path.join(base, gl), recursive=True):
            ap = os.path.abspath(fp)
            if ap not in seen:
                seen.add(ap)
                files.append(ap)
    sessions, dropped = [], 0
    for fp in files:
        try:
            fmtime = os.path.getmtime(fp)
        except OSError:
            continue
        # lenient mtime prefilter (window + 1d slack); precise ts filter per line
        if fmtime < cutoff_s - 86400:
            continue
        s = Sess(prov.get("name", "Pi"), os.path.splitext(os.path.basename(fp))[0])
        s.source_type = prov.get("source_type", "cli")
        s.billing = pbilling
        s.project = basename_project(os.path.dirname(fp))
        ctx_provider, ctx_model = "", ""
        touched = False
        try:
            with open(fp, errors="replace") as f:
                for line in f:
                    if '"model_change"' not in line and '"message"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    typ = o.get("type")
                    if typ == "model_change":
                        prov_raw = (o.get("provider") or "").lower()
                        ctx_provider = PI_PROVIDER_MAP.get(prov_raw, prov_raw)
                        ctx_model = o.get("modelId") or o.get("model") or ctx_model
                        continue
                    if typ != "message":
                        continue
                    msg = o.get("message") or {}
                    if (msg.get("role") or o.get("role")) != "assistant":
                        continue
                    u = msg.get("usage") or o.get("usage") or {}
                    if not u:
                        continue
                    prov_raw = (msg.get("provider") or o.get("provider") or "").lower()
                    if prov_raw:
                        fam = PI_PROVIDER_MAP.get(prov_raw)
                        if fam is None:
                            dropped += 1   # provider present but unmapped → drop
                            continue
                    else:
                        fam = ctx_provider or None
                    mdl = (msg.get("model") or o.get("model") or msg.get("modelId")
                           or o.get("modelId") or ctx_model)
                    if not mdl and not fam:
                        continue
                    ts = parse_epoch_or_iso(msg.get("timestamp") or o.get("timestamp"))
                    if ts is None or ts < cutoff_s or ts > end_s:
                        continue
                    rec = {"usage": u}
                    inp = get_first(rec, PI_USAGE["input"], 0) or 0
                    cr = get_first(rec, PI_USAGE["cache_read"], 0) or 0
                    cw = get_first(rec, PI_USAGE["cache_write"], 0) or 0
                    out = get_first(rec, PI_USAGE["output"], 0) or 0
                    if not (inp or out or cr or cw):
                        continue
                    fam = fam or model_key(mdl, pricing).split("-")[0]
                    if fam == "codex" or (mdl and "gpt" in mdl.lower()):
                        # Codex bills cache-write at input rate; no separate write.
                        t = {"input": inp + cw, "output": out, "cache_read": cr,
                             "cache_write_5m": 0, "cache_write_1h": 0}
                        cmodel = mdl or "gpt-5.5"
                    else:
                        t = {"input": inp, "output": out, "cache_read": cr,
                             "cache_write_5m": cw, "cache_write_1h": 0}
                        cmodel = mdl or "claude-opus-4"
                    s.model = s.model or cmodel
                    accrue(s, t, cmodel, pricing, ts)
                    touched = True
        except OSError as e:
            warnings.append(f"pi {os.path.basename(fp)}: {e}")
            continue
        if touched:
            s.model_key = model_key(s.model, pricing)
            s.title = s.title or s.project or s.id[:8]
            sessions.append(s)
    if dropped:
        warnings.append(f"Pi: dropped {dropped} message(s) with an unmapped "
                        f"provider tag (can't price). Add it to PI_PROVIDER_MAP.")
    return sessions


def read_opencode_sqlite(prov, cutoff_s, end_s, pricing, warnings):
    """OpenCode-Go local SQLite (~/.local/share/opencode/opencode.db). Like
    CodexBar's OpenCodeGoLocalUsageReader, this DB stores a PRE-COMPUTED USD
    `cost` per assistant message (no token breakdown), so we book the dollars
    directly — tokens stay 0 and these sessions won't appear in token charts.
    Cost is real spend → metered billing."""
    db = None
    for base, _gl in expand_roots(prov.get("roots")):
        cand = base if base.endswith(".db") else os.path.join(base, "opencode.db")
        if os.path.exists(cand):
            db = cand
            break
    if not db:
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        warnings.append(f"OpenCode DB open failed: {e}")
        return []
    name = prov.get("name", "OpenCode")
    pid = prov.get("opencode_provider_id", "opencode-go")
    out = []
    try:
        tbls = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "message" not in tbls:
            warnings.append("OpenCode DB has no `message` table; skipped.")
            return []
        s = Sess(name, "opencode-go")
        s.source_type = prov.get("source_type", "cli")
        s.billing = prov.get("billing", "metered")
        s.model = prov.get("model", "opencode")
        rows = con.execute(
            "SELECT json_extract(data,'$.cost') AS cost, "
            "COALESCE(json_extract(data,'$.time.created'), time_created) AS ts, "
            "json_extract(data,'$.modelID') AS model "
            "FROM message WHERE json_extract(data,'$.role')='assistant' "
            "AND json_extract(data,'$.providerID')=?", (pid,))
        for r in rows:
            cost = r["cost"] if "cost" in r.keys() else None
            if not cost:
                continue
            ts = r["ts"]
            ts = ts / 1000.0 if isinstance(ts, (int, float)) and ts > 1e12 else ts
            ts = parse_epoch_or_iso(ts)
            if ts is None or ts < cutoff_s or ts > end_s:
                continue
            s.est_cost += float(cost)
            s.turns += 1
            s.first_ts = min(s.first_ts or ts, ts)
            s.last_ts = max(s.last_ts or ts, ts)
            if r["model"]:
                s.model = r["model"]
        if s.turns:
            s.model_key = model_key(s.model, pricing)
            s.title = name + " (USD-only, no token breakdown)"
            out.append(s)
    except sqlite3.Error as e:
        warnings.append(f"OpenCode DB read failed: {e}")
    finally:
        con.close()
    return out


def _parse_openclaw_native(fp, cutoff_s, end_s, pricing, warnings, name):
    """One OpenClaw native session file → Sess (or None). Handles BOTH native
    schemas: trajectory events (`type:"model.completed"`, `data.usage`) and the
    newer message log (`model_change` ctx + `type:"message"` with
    `message.usage`). Rows whose provider is openai-codex/openai are SKIPPED here
    because the same turns are already counted via the agent's nested codex-home
    (avoids double-counting); only non-Codex backends (anthropic/bedrock/…) are
    booked. Priced by model name; billing derived from model family."""
    s = Sess(name, os.path.splitext(os.path.basename(fp))[0])
    s.source_type = "openclaw"
    # fp = <root>/agents/<agent>/sessions/<file>; project = the agent name
    s.project = basename_project(os.path.dirname(os.path.dirname(fp)))
    ctx_provider = ""
    ctx_model = ""
    touched = False

    def book(prov_raw, mdl, u, ts):
        nonlocal touched
        if (prov_raw or "") in ("openai-codex", "openai"):
            return  # already in codex-home; skip to avoid double count
        if ts is None or ts < cutoff_s or ts > end_s:
            return
        inp = u.get("input", 0) or 0
        cr = u.get("cacheRead", 0) or 0
        cw = u.get("cacheWrite", 0) or 0
        out = u.get("output", 0) or 0
        if not (inp or out or cr or cw):
            return
        t = {"input": inp, "output": out, "cache_read": cr,
             "cache_write_5m": cw, "cache_write_1h": 0}
        mm = mdl or ctx_model or ""
        s.model = s.model or mm
        accrue(s, t, mm or s.model, pricing, ts)
        touched = True

    def set_title(txt):
        cand = _openclaw_clean_title(txt if isinstance(txt, str) else "")
        if not s.title and cand:
            s.title = cand[:80]

    def msg_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    t = b.get("text") or b.get("content")
                    if isinstance(t, str) and t.strip():
                        return t
                elif isinstance(b, str) and b.strip():
                    return b
        return ""

    try:
        with open(fp, errors="replace") as f:
            for line in f:
                if ('"model.completed"' not in line and '"model_change"' not in line
                        and '"message"' not in line and '"prompt.submitted"' not in line):
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                typ = o.get("type")
                if typ == "model_change":
                    ctx_provider = (o.get("provider") or "").lower()
                    ctx_model = o.get("modelId") or o.get("model") or ctx_model
                elif typ == "prompt.submitted":      # trajectory: readable title
                    set_title((o.get("data") or {}).get("prompt"))
                elif typ == "model.completed":
                    book((o.get("provider") or "").lower(),
                         o.get("modelId"),
                         (o.get("data") or {}).get("usage") or {},
                         parse_epoch_or_iso(o.get("ts") or o.get("timestamp")))
                elif typ == "message":
                    msg = o.get("message") or {}
                    role = msg.get("role") or o.get("role")
                    if role == "user":               # message log: readable title
                        set_title(msg_text(msg.get("content") or o.get("content")))
                        continue
                    if role != "assistant":
                        continue
                    book((msg.get("provider") or o.get("provider") or ctx_provider or "").lower(),
                         msg.get("model") or o.get("model"),
                         msg.get("usage") or {},
                         parse_epoch_or_iso(o.get("timestamp") or msg.get("timestamp")))
    except OSError as e:
        warnings.append(f"openclaw {os.path.basename(fp)}: {e}")
        return None
    if not touched:
        return None
    s.model_key = model_key(s.model, pricing)
    s.title = s.title or s.project or s.id[:8]
    return s


def openclaw_roots(prov):
    roots = prov.get("roots") or [{"env": "OPENCLAW_HOME", "path": "~/.openclaw"}]
    return [b for b, _ in expand_roots(roots) if os.path.isdir(b)]


def read_openclaw(prov, cutoff_s, end_s, pricing, warnings):
    """OpenClaw agent framework (~/.openclaw). Two data sources, deduped:
      1. Each agent's NESTED codex-home (agents/*/agent/codex-home) is a standard
         Codex rollout store → reuse the Codex parser (per-home priority via that
         home's logs_2.sqlite). This is authoritative for codex-backed turns.
      2. Native session logs (agents/*/sessions/*.jsonl) for NON-codex backends
         (anthropic/bedrock/…); codex rows there are skipped (already in #1).
    Everything is attributed to one source (the provider name). No-op if absent."""
    name = prov.get("name", "OpenClaw")
    pbilling = prov.get("billing", "")   # "" → derive from model family
    bases = openclaw_roots(prov)
    if not bases:
        return []
    mtime_slack = (end_s - cutoff_s) + 86400
    sessions = []
    seen_ids = set()
    # 1. nested codex-homes
    for base in bases:
        for ch in sorted(glob.glob(os.path.join(base, "agents", "*", "agent", "codex-home"))):
            tier = codex_service_tier(os.path.join(ch, "config.toml"))
            pri, std = codex_priority_turns(cutoff_s, os.path.join(ch, "logs_2.sqlite"))
            for fp, is_archived in sorted(_codex_files([ch]).items()):
                try:
                    if not is_archived and os.path.getmtime(fp) < cutoff_s - mtime_slack:
                        continue
                except OSError:
                    continue
                s = _parse_codex_file(fp, None, cutoff_s, end_s, pricing, warnings,
                                      tier, pri, std, name, False)
                if s is None or s.id in seen_ids:
                    continue
                seen_ids.add(s.id)
                if pbilling:
                    s.billing = pbilling
                sessions.append(s)
    # 2. native non-codex sessions
    for base in bases:
        for fp in sorted(glob.glob(os.path.join(base, "agents", "*", "sessions", "*.jsonl"))):
            ap = os.path.abspath(fp)
            sid = os.path.splitext(os.path.basename(fp))[0]
            if sid in seen_ids:
                continue
            try:
                if os.path.getmtime(ap) < cutoff_s - mtime_slack:
                    continue
            except OSError:
                continue
            s = _parse_openclaw_native(ap, cutoff_s, end_s, pricing, warnings, name)
            if s is None:
                continue
            seen_ids.add(sid)
            if pbilling:
                s.billing = pbilling
            sessions.append(s)
    # OpenClaw agent runs often have no clean human title (each codex turn is
    # prefixed with an OpenClaw runtime-context blob). When the title degraded to
    # the bare agent/cwd, make rows distinguishable with the start time.
    for s in sessions:
        if s.title == s.project and s.first_ts:
            s.title = f"{s.project} · {datetime.fromtimestamp(s.first_ts):%m-%d %H:%M}"
    return sessions


FORMAT_READERS = {
    "generic_jsonl": read_generic_jsonl,
    "pi_jsonl": read_pi,
    "opencode_sqlite": read_opencode_sqlite,
    "openclaw": read_openclaw,
}


def provider_installed(prov, ctx):
    """Best-effort 'is this tool present on disk' check, for the coverage map.
    Built-ins use their dedicated root logic; config formats use `roots`."""
    fmt = prov.get("format")
    if fmt == "builtin:claude":
        return any(os.path.isdir(r) for r in claude_project_roots())
    if fmt == "builtin:codex":
        return bool(codex_roots(ctx))
    if fmt == "builtin:xdt":
        return bool(ctx.get("db_path"))
    if fmt == "openclaw":
        return bool(openclaw_roots(prov))
    for base, gl in expand_roots(prov.get("roots")):
        if base.endswith(".db"):
            if os.path.exists(base):
                return True
        elif os.path.isdir(base):
            if glob.glob(os.path.join(base, gl), recursive=True):
                return True
            if fmt == "opencode_sqlite" and os.path.exists(
                    os.path.join(base, "opencode.db")):
                return True
    return False


def provider_coverage(providers, ctx, sessions):
    """One row per known local-log (token-cost) provider: did it contribute data
    in this window, is it installed-but-empty, not installed, or disabled? Makes
    the report show WHAT WAS CHECKED, not just what was found."""
    by_src = defaultdict(lambda: {"cost": 0.0, "n": 0, "tok": 0})
    for s in sessions:
        a = by_src[s.source]
        a["cost"] += s.cost
        a["n"] += 1
        a["tok"] += total_tokens(s.tok)
    rows = []
    for prov in providers:
        name = prov.get("name", "?")
        if name.startswith("_"):
            continue   # example/template entries
        hit = by_src.get(name)
        if not prov.get("enabled", True):
            status, detail = "未启用", "registry 中 enabled:false"
        elif hit and (hit["cost"] > 0 or hit["n"] > 0):
            status = "有数据"
            detail = (f"{fmt_usd(hit['cost'])} · {hit['n']} session · "
                      f"{fmt_tok(hit['tok'])} tok")
        elif provider_installed(prov, ctx):
            status, detail = "已装·窗口内无数据", "本地有该工具,但所选时间窗内无用量"
        else:
            status, detail = "未安装", "本机未发现其数据(roots 不存在)"
        rows.append({"name": name, "billing": prov.get("billing", ""),
                     "coverage": prov.get("coverage", "token-cost"),
                     "verified": prov.get("format_verified", None),
                     "status": status, "detail": detail})
    return rows


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #
def positive_int(value):
    try:
        n = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("must be an integer") from e
    if n <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return n


def main():
    ap = argparse.ArgumentParser(description="Audit recent AI spend.")
    ap.add_argument("--days", type=positive_int, default=7)
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (default: now)")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--pricing", default=os.path.join(SKILL_DIR, "pricing.json"))
    ap.add_argument("--providers", default=os.path.join(SKILL_DIR, "providers.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--source", default=None,
                    help="scope the report to one host App (substring of source "
                         "name, e.g. 'openclaw'). Default: all sources.")
    args = ap.parse_args()

    try:
        end_s = (datetime.strptime(args.end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59).timestamp() if args.end else time.time())
    except ValueError:
        ap.error("--end must be YYYY-MM-DD")
    cutoff_s = end_s - args.days * 86400
    try:
        pricing = load_pricing(args.pricing)
        _pj = json.load(open(args.pricing))
        pricing_version = _pj.get("pricing_version", "?")
        billing = _pj.get("billing", {})
    except (OSError, json.JSONDecodeError, KeyError) as e:
        ap.error(f"failed to load pricing file {args.pricing}: {e}")
    warnings = []

    ctx = read_xdt_context(cutoff_s, end_s, warnings)
    seen_sdk = set()
    claude = read_claude(ctx, cutoff_s, end_s, pricing, warnings, seen_sdk)
    codex = read_codex(ctx, cutoff_s, end_s, pricing, warnings)
    for s in codex:
        # Every codex rollout (XDT-orca or standalone) is now counted here, so
        # mark its id covered to keep the agent_meta fallback from re-adding it.
        seen_sdk.add(s.id)
    fallback = read_xdt_agent_meta_fallback(ctx, cutoff_s, end_s, pricing,
                                            seen_sdk, warnings)
    sessions = claude + codex + fallback

    # Extra config-driven providers. Built-in formats (claude/codex/xdt) are
    # handled above; here we dispatch the local-log token-cost adapters
    # (generic_jsonl / pi_jsonl / opencode_sqlite). Absent tools no-op silently.
    # Tools with no local token log (Gemini/Amp/Grok/Cursor/Copilot/…) expose
    # only an authenticated quota API and are intentionally OUT OF SCOPE.
    providers = load_providers(args.providers)
    for prov in providers:
        if not prov.get("enabled", True):
            continue
        reader = FORMAT_READERS.get(prov.get("format"))
        if reader:
            sessions += reader(prov, cutoff_s, end_s, pricing, warnings)

    # Surface models with no real pricing entry (using the _default fallback).
    # Per the pricing rule (see SKILL.md): never guess from memory — look up the
    # official rate and update pricing.json before trusting these dollars.
    def _priced(m):
        k = model_key(m, pricing)
        return k != "_default" and k in pricing

    unknown = sorted({s.model for s in sessions if s.model and not _priced(s.model)})
    if unknown:
        warnings.append(
            "UNKNOWN MODEL PRICING (using _default fallback — dollars for these "
            "are NOT reliable): " + ", ".join(unknown)
            + ". Look up the official price (XDT modelCost.ts / vendor pricing "
            "page) and update pricing.json, then re-run.")

    # --source: scope the whole report to one host App (case-insensitive substring
    # of the source name, e.g. "openclaw"). Useful for auditing a single tool, or
    # for keeping a remote run focused on one source without other users' data.
    if args.source:
        want = args.source.lower()
        sessions = [s for s in sessions if want in (s.source or "").lower()]
        warnings.append(f"已用 --source 过滤:只保留来源含 '{args.source}' 的 session"
                        f"(共 {len(sessions)} 个)。")

    apply_schedule_metadata(ctx, sessions)
    sess_by_sdk = {s.id: s for s in sessions}
    sched = build_schedule_report(ctx, sess_by_sdk, sessions)

    cfg = {
        "window_label": f"最近 {args.days} 天 "
        f"({datetime.fromtimestamp(cutoff_s):%Y-%m-%d} → "
        f"{datetime.fromtimestamp(end_s):%Y-%m-%d})",
        "now_str": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pricing_version": pricing_version,
        "billing": billing,
        "top": args.top,
        "low_cache_ratio": 0.5, "low_cache_min_cost": 1.0,
        "small_output": 3000, "small_turns": 6, "small_cost": 0.50,
        "runaway_mult": 6.0, "runaway_min_cost": 5.0,
        "dialogue_breakout_cost": 2.0,
        # Waste lists: only individually show items worth a human's attention —
        # metered (real cash) ≥ waste_list_min, subscription ($0 marginal) ≥
        # waste_sub_list_min; cap each list, summarize the rest.
        "waste_list_min": 3.0, "waste_sub_list_min": 15.0, "waste_list_top": 6,
        "coverage": provider_coverage(providers, ctx, sessions),
    }
    flags, median_cost = detect_waste(sessions, cfg)
    report = render(sessions, ctx, sched, flags, median_cost, cfg, warnings)

    if not args.quiet:
        print(report)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        stamp = datetime.fromtimestamp(end_s).strftime("%Y%m%d")
        base = os.path.join(args.out, f"spend-{args.days}d-{stamp}")
        with open(base + ".md", "w") as f:
            f.write(report)
        # --out writes the markdown report only. Need the structured per-session
        # JSON? Use --json (stdout) and redirect it — we don't litter a .json file.
        ab = os.path.abspath(base)
        if args.json:
            with open(base + ".json", "w") as f:
                json.dump(to_json(sessions, ctx, sched, flags, cfg, warnings),
                          f, indent=2, ensure_ascii=False)
        # Emit an absolute file:// URL so the host chat renders a clickable link.
        # A `dir/file.{md,json}` brace shorthand is NOT a real path and won't
        # linkify — always give the full URL(s), one per line.
        msg = f"\n[saved] file://{ab}.md"
        if args.json:
            msg += f"\n[saved] file://{ab}.json"
        print(msg, file=sys.stderr)
    if args.json:
        print("\n" + json.dumps(
            to_json(sessions, ctx, sched, flags, cfg, warnings),
            indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
