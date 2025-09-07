from utils.shell import is_safe_command, run_shell_safe


def test_refusal_blocks_dangerous_command(tmp_path, monkeypatch):
    monkeypatch.setenv("LINOPS_AUDIT_DIR", str(tmp_path))
    ok, reason = is_safe_command("rm -rf / --no-preserve-root")
    assert ok is False and "blocked token" in reason
    res = run_shell_safe("rm -rf / --no-preserve-root", dry_run=False)
    assert res.get("refused") is True
    assert res.get("ok") is False


def test_dry_run_and_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("LINOPS_AUDIT_DIR", str(tmp_path))
    res1 = run_shell_safe("echo hello", dry_run=True)
    assert res1["ok"] is True and res1["dry_run"] is True
    res2 = run_shell_safe("echo hello", dry_run=False)
    assert res2["ok"] is True and res2["rc"] == 0 and "hello" in res2["stdout"]
