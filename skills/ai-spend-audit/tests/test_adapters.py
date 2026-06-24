#!/usr/bin/env python3
"""Self-contained adapter tests for ai-spend-audit's local-log readers.

Builds tiny synthetic fixtures (Pi JSONL, OpenCode-Go sqlite, a generic
alias-mapped JSONL) in a tempdir, points a throwaway providers.json at them,
runs analyze.py over a wide window, and asserts the per-adapter dollars / billing
/ token handling. No real AI tool needs to be installed — this exercises the
adapters in isolation. Run: python3 tests/test_adapters.py
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ANALYZE = os.path.join(SKILL, "scripts", "analyze.py")
PRICING = os.path.join(SKILL, "pricing.json")

# 2026-06-03 ~10:00Z, comfortably inside the test window (--end 2026-06-04).
TS_ISO = "2026-06-03T10:00:00Z"
TS_MS = 1764756000000  # 2026-06-03T10:00:00Z in epoch ms


def approx(a, b, tol=1e-4):
    return abs(a - b) <= tol


def build_fixtures(root):
    # --- Pi: model_change context + assistant messages, mixed upstreams ---
    pidir = os.path.join(root, "pi", "agent", "sessions")
    os.makedirs(pidir)
    pi_lines = [
        {"type": "model_change", "provider": "anthropic",
         "modelId": "claude-opus-4-5", "timestamp": TS_ISO},
        {"type": "message", "timestamp": "2026-06-03T10:00:05Z",
         "message": {"role": "assistant", "model": "claude-opus-4-5",
                     "usage": {"input": 1000, "output": 500,
                               "cacheRead": 200, "cacheWrite": 100}}},
        {"type": "model_change", "provider": "openai-codex",
         "modelId": "gpt-5.5", "timestamp": "2026-06-03T10:01:00Z"},
        {"type": "message", "timestamp": "2026-06-03T10:01:05Z",
         "message": {"role": "assistant", "model": "gpt-5.5",
                     "usage": {"inputTokens": 2000, "outputTokens": 800,
                               "cacheReadInputTokens": 300}}},
        # provider present but unknown -> must be DROPPED
        {"type": "message", "timestamp": "2026-06-03T10:02:00Z",
         "message": {"role": "assistant", "provider": "some-unknown",
                     "model": "x", "usage": {"input": 10, "output": 10}}},
        # non-assistant -> skipped
        {"type": "message", "timestamp": "2026-06-03T10:03:00Z",
         "message": {"role": "user", "content": "hi"}},
    ]
    with open(os.path.join(pidir, "2026-06-03T10-00-00-000Z_sess.jsonl"), "w") as f:
        for o in pi_lines:
            f.write(json.dumps(o) + "\n")

    # --- OpenCode-Go: sqlite with pre-computed USD cost per assistant message ---
    ocdir = os.path.join(root, "opencode")
    os.makedirs(ocdir)
    db = os.path.join(ocdir, "opencode.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE message (id TEXT, time_created INTEGER, data TEXT)")
    for cost, mdl in ((0.12, "claude-sonnet-4-5"), (0.08, "gpt-5.5")):
        data = json.dumps({"role": "assistant", "providerID": "opencode-go",
                           "cost": cost, "modelID": mdl,
                           "time": {"created": TS_MS}})
        con.execute("INSERT INTO message VALUES (?,?,?)", ("m", TS_MS, data))
    # noise: a non-opencode-go row and a user row must be ignored
    con.execute("INSERT INTO message VALUES (?,?,?)", ("n", TS_MS, json.dumps(
        {"role": "assistant", "providerID": "other", "cost": 9.99})))
    con.commit()
    con.close()

    # --- Generic: a tool with quirky field names, aliases + cached_in_input ---
    gdir = os.path.join(root, "generic")
    os.makedirs(gdir)
    with open(os.path.join(gdir, "log.jsonl"), "w") as f:
        f.write(json.dumps({"ts": "2026-06-03T11:00:00Z", "model": "gemini-3-pro",
                            "usage": {"in": 5000, "out": 1000, "cr": 2000}}) + "\n")

    providers = {"providers": [
        {"name": "FixturePi", "format": "pi_jsonl", "billing": "subscription",
         "enabled": True, "roots": [{"path": pidir, "glob": "**/*.jsonl"}]},
        {"name": "FixtureOpenCode", "format": "opencode_sqlite", "billing": "metered",
         "enabled": True, "opencode_provider_id": "opencode-go",
         "roots": [{"path": ocdir, "glob": "*.db"}]},
        {"name": "FixtureGeneric", "format": "generic_jsonl", "billing": "metered",
         "enabled": True, "model": "gemini-3-pro",
         "roots": [{"path": gdir, "glob": "**/*.jsonl"}],
         "fields": {"ts": "ts", "model": "model",
                    "input": ["usage.in", "usage.input"], "output": ["usage.out"],
                    "cache_read": ["usage.cr"], "cached_in_input": True}},
    ]}
    # --- OpenClaw: nested codex-home + native trajectory + native message ---
    ocl = os.path.join(root, "openclaw")
    # (1) agent A: nested standard codex-home rollout
    chs = os.path.join(ocl, "agents", "agentA", "agent", "codex-home",
                       "sessions", "2026", "06", "03")
    os.makedirs(chs)
    with open(os.path.join(chs, "rollout-2026-06-03T10-00-00-sesscx.jsonl"), "w") as f:
        for o in [
            {"type": "session_meta", "timestamp": TS_ISO,
             "payload": {"id": "sess-cx", "cwd": "/work/proj", "model": "gpt-5.5"}},
            {"type": "turn_context", "timestamp": TS_ISO,
             "payload": {"model": "gpt-5.5", "turn_id": "t1", "effort": "high"}},
            {"type": "response_item", "role": "user",
             "content": [{"type": "input_text", "text": "build the auth module"}]},
            {"type": "event_msg", "timestamp": "2026-06-03T10:00:05Z",
             "payload": {"type": "token_count", "info": {"last_token_usage": {
                 "input_tokens": 1000, "cached_input_tokens": 200,
                 "output_tokens": 500}}}},
        ]:
            f.write(json.dumps(o) + "\n")
    # (2) agent B: native trajectory, non-codex backend (anthropic)
    bsess = os.path.join(ocl, "agents", "agentB", "sessions")
    os.makedirs(bsess)
    with open(os.path.join(bsess, "traj1.trajectory.jsonl"), "w") as f:
        f.write(json.dumps({"type": "prompt.submitted", "ts": "2026-06-03T10:59:00Z",
                            "data": {"prompt": "summarize the logs"}}) + "\n")
        f.write(json.dumps({"type": "model.completed", "provider": "anthropic",
                            "modelId": "claude-sonnet-4-5", "ts": "2026-06-03T11:00:00Z",
                            "data": {"usage": {"input": 2000, "output": 300,
                                               "cacheRead": 1000}}}) + "\n")
    # (3) agent C: native message log — anthropic row counts, openai-codex row SKIP
    csess = os.path.join(ocl, "agents", "agentC", "sessions")
    os.makedirs(csess)
    with open(os.path.join(csess, "msg1.jsonl"), "w") as f:
        for o in [
            {"type": "model_change", "provider": "anthropic", "modelId": "claude-opus-4-5"},
            {"type": "message", "timestamp": "2026-06-03T12:00:00Z",
             "message": {"role": "assistant", "provider": "anthropic",
                         "model": "claude-opus-4-5",
                         "usage": {"input": 1000, "output": 200, "cacheRead": 0, "cacheWrite": 0}}},
            {"type": "message", "timestamp": "2026-06-03T12:01:00Z",
             "message": {"role": "assistant", "provider": "openai-codex", "model": "gpt-5.5",
                         "usage": {"input": 99999, "output": 99999}}},
        ]:
            f.write(json.dumps(o) + "\n")
    providers["providers"].append(
        {"name": "FixtureOpenClaw", "format": "openclaw", "billing": "",
         "enabled": True, "roots": [{"path": ocl, "glob": "**/*.jsonl"}]})

    pj = os.path.join(root, "providers.test.json")
    with open(pj, "w") as f:
        json.dump(providers, f)
    return pj


def run(providers_path):
    out = subprocess.check_output(
        [sys.executable, ANALYZE, "--days", "3650", "--end", "2026-06-04",
         "--providers", providers_path, "--pricing", PRICING, "--json", "--quiet"],
        text=True)
    # analyze prints the report then "\n" + json when --json; here --quiet
    # suppresses the report, so stdout is just the JSON document.
    return json.loads(out)


def main():
    fails = []

    def check(name, cond, detail=""):
        (print(f"  ok  {name}") if cond
         else (fails.append(name), print(f" FAIL {name}: {detail}")))

    with tempfile.TemporaryDirectory() as root:
        pj = build_fixtures(root)
        d = run(pj)
        by = {}
        for s in d["sessions"]:
            by.setdefault(s["source"], []).append(s)

        # ---- Pi ----
        pi = by.get("FixturePi", [])
        check("pi: one session", len(pi) == 1, f"got {len(pi)}")
        if pi:
            s = pi[0]
            # anthropic msg: 1000*5 +200*0.5 +100*6.25 +500*25 = 18225 -> 0.018225
            # codex msg:     2000*5 +300*0.5 +800*30           = 34150 -> 0.034150
            exp = (18225 + 34150) / 1e6
            check("pi: cost folds codex+anthropic billing", approx(s["est_cost"], exp),
                  f"{s['est_cost']} != {exp}")
            check("pi: billing=subscription (Pi plan)", s["billing"] == "subscription",
                  s["billing"])
            check("pi: turns=2 (unknown+user dropped)", s["turns"] == 2, s["turns"])
        check("pi: dropped-unmapped warning",
              any("unmapped provider" in w for w in d["warnings"]))

        # ---- OpenCode-Go ----
        oc = by.get("FixtureOpenCode", [])
        check("opencode: one session", len(oc) == 1, f"got {len(oc)}")
        if oc:
            s = oc[0]
            check("opencode: USD booked directly (0.12+0.08)",
                  approx(s["est_cost"], 0.20), s["est_cost"])
            check("opencode: billing=metered (real $)", s["billing"] == "metered",
                  s["billing"])
            check("opencode: no token breakdown",
                  sum(s["tokens"].values()) == 0, s["tokens"])
            check("opencode: ignores non-opencode-go rows", s["turns"] == 2, s["turns"])

        # ---- Generic w/ aliases + cached_in_input ----
        g = by.get("FixtureGeneric", [])
        check("generic: one session", len(g) == 1, f"got {len(g)}")
        if g:
            s = g[0]
            # cached_in_input: input 5000-2000=3000; gemini-pro 2/12/0.2:
            # 3000*2 + 2000*0.2 + 1000*12 = 18400 -> 0.0184
            check("generic: alias map + cached_in_input", approx(s["est_cost"], 0.0184),
                  s["est_cost"])
            check("generic: routed to gemini-pro pricing",
                  s["tokens"]["input"] == 3000 and s["tokens"]["cache_read"] == 2000,
                  s["tokens"])

        # ---- OpenClaw: codex-home + native, with dedup of codex rows ----
        oc = by.get("FixtureOpenClaw", [])
        check("openclaw: 3 sessions (codex-home + 2 native)", len(oc) == 3,
              f"got {len(oc)}")
        byid = {s["id"]: s for s in oc}
        cx = byid.get("sess-cx")
        # codex-home: 800*5 + 200*0.5 + 500*30 = 19100 -> 0.0191, subscription
        check("openclaw: nested codex-home priced via Codex parser",
              cx is not None and approx(cx["est_cost"], 0.0191), cx)
        check("openclaw: codex title = first user message (not cwd)",
              cx is not None and cx["title"] == "build the auth module",
              cx and cx["title"])
        check("openclaw: codex turn = subscription billing",
              cx is not None and cx["billing"] == "subscription" and cx["source_type"] == "codex",
              cx and (cx["billing"], cx["source_type"]))
        tj = byid.get("traj1.trajectory")
        # trajectory anthropic sonnet: 2000*3 + 1000*0.3 + 300*15 = 10800 -> 0.0108
        check("openclaw: native trajectory (anthropic) counted",
              tj is not None and approx(tj["est_cost"], 0.0108), tj)
        check("openclaw: trajectory title = prompt.submitted (not cwd)",
              tj is not None and tj["title"] == "summarize the logs",
              tj and tj["title"])
        check("openclaw: native row = metered (claude) + source_type openclaw",
              tj is not None and tj["billing"] == "metered" and tj["source_type"] == "openclaw",
              tj and (tj["billing"], tj["source_type"]))
        mg = byid.get("msg1")
        # message: anthropic opus 1000*5 + 200*25 = 10000 -> 0.01; the openai-codex
        # row (99999/99999) MUST be skipped (already in codex-home) -> stays 0.01
        check("openclaw: native message anthropic counted, openai-codex row SKIPPED",
              mg is not None and approx(mg["est_cost"], 0.01) and mg["turns"] == 1,
              mg and (mg["est_cost"], mg["turns"]))

    print()
    if fails:
        print(f"FAILED ({len(fails)}): " + ", ".join(fails))
        sys.exit(1)
    print("ALL ADAPTER TESTS PASSED")


if __name__ == "__main__":
    main()
