#!/usr/bin/env bash
# Run the ai-spend-audit test suite (offline, no real AI tool needed).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
echo "== py_compile =="
python3 -m py_compile "$SKILL"/scripts/analyze.py
echo "OK"
echo "== JSON validity =="
for f in pricing.json providers.json; do
  python3 -c "import json;json.load(open('$SKILL/$f'));print('  ok  $f')"
done
echo "== adapter tests =="
python3 "$HERE/test_adapters.py"
echo
echo "ALL GREEN"
