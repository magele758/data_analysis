#!/bin/sh
# Local counterparts of the three CI gates. See .github/workflows/ci.yml.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
gate=${1:-fast}

case "$gate" in
  fast)
    python3 -m compileall -q app
    find app/web/static -name '*.js' -print0 | xargs -0 -n1 node --check
    .venv/bin/pytest tests/test_dashboard_nav.py -q --tb=short
    ;;
  merge)
    .venv/bin/pytest tests/ -m "not full" -q --tb=short
    ;;
  full)
    .venv/bin/pytest tests/ -q --tb=short
    ;;
  *)
    echo "usage: $0 fast|merge|full" >&2
    exit 2
    ;;
esac
