Quick Demo

1. Plan a runbook:
   python -m cli.main plan "free disk and check cpu/mem"

2. Guardrail refusal (proof of safety):
   python -m cli.main call "rm -rf / --no-preserve-root"

3. Preview (dry-run by default):
   python -m cli.main do "free disk and check cpu/mem"

4. Simulate crash and auto-heal:
   python - <<'PY'
   from utils.shell import run_shell_safe
   from runbooks.fakesvc import DEFAULT_PIDFILE
   run_shell_safe(f"kill -9 $(cat {DEFAULT_PIDFILE}) 2>/dev/null || true", dry_run=False)
   PY
   python -m cli.main do "web server crashed, restart and verify" --yes

5. Audit trail:
   tail -n 30 audit/audit.jsonl

One-click:
make demo
