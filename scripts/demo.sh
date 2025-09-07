#!/usr/bin/env bash
set -euo pipefail

mkdir -p demo/sample_artifacts audit

echo "== plan"
python -m cli.main plan "free disk and check cpu/mem" | tee demo/sample_artifacts/plan.json

echo "== refusal (safe shell)"
python -m cli.main call "rm -rf / --no-preserve-root" | tee demo/sample_artifacts/refusal.json

echo "== do (dry-run)"
python -m cli.main do "free disk and check cpu/mem" | tee demo/sample_artifacts/do_dryrun.json

echo "== simulate crash"
python - <<'PY'
from utils.shell import run_shell_safe
from runbooks.fakesvc import DEFAULT_PIDFILE
run_shell_safe(f"kill -9 $(cat {DEFAULT_PIDFILE}) 2>/dev/null || true", dry_run=False)
PY

echo "== heal + verify (--yes)"
python -m cli.main do "web server crashed, restart and verify" --yes | tee demo/sample_artifacts/heal.json

echo "== audit tail"
tail -n 30 audit/audit.jsonl | tee demo/sample_artifacts/audit_tail.txt

echo "Done."
