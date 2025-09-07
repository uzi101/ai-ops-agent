import time
from utils.shell import run_shell_safe
from runbooks.fakesvc import heal_fakesvc_8080, DEFAULT_PIDFILE


def test_heal_fakesvc_dryrun_then_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("LINOPS_AUDIT_DIR", str(tmp_path))
    run_shell_safe(
        f"kill -9 $(cat {DEFAULT_PIDFILE}) 2>/dev/null || true", dry_run=False)
    r1 = heal_fakesvc_8080(dry_run=True)
    assert isinstance(r1, dict) and "verify" in r1
    r2 = heal_fakesvc_8080(dry_run=False)
    assert r2["ok"] is True and r2["verify"]["ok"] is True
    time.sleep(0.2)
    r3 = heal_fakesvc_8080(dry_run=True)
    assert r3["ok"] is True
