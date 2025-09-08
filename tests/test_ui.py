# tests/test_ui.py
from typer.testing import CliRunner
import cli.main as cli
from cli.ui import show_plan, show_results, show_refusal


def test_show_plan_renders_table(capsys):
    show_plan([{"name": "free_disk", "kwargs": {}}, {
              "name": "check_cpu_mem", "kwargs": {}}])
    out = capsys.readouterr().out
    assert "Planned Runbook" in out
    assert "free_disk" in out
    assert "check_cpu_mem" in out


def test_show_refusal_renders_panel(capsys):
    show_refusal("rm -rf / --no-preserve-root", "blocked token: rm -rf /")
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "blocked token: rm -rf /" in out
    assert "rm -rf / --no-preserve-root" in out


def test_show_results_renders_applied_and_preview(capsys):
    show_results(
        [
            {"step": "free_disk", "ok": True,
                "dry_run": True, "msg": "would run df -h /"},
            {"step": "heal_fakesvc_8080", "ok": True,
                "stdout": "pid=1234 verify=ok"},
        ],
        dry_run=False,
    )
    out = capsys.readouterr().out
    assert "Execution (applied)" in out
    assert "free_disk" in out and "preview" in out
    assert "heal_fakesvc_8080" in out and "exec" in out
    assert "would run df -h /" in out
    assert "pid=1234" in out and "verify=ok" in out


def test_cli_pretty_plan_and_call_and_do():
    runner = CliRunner()
    r1 = runner.invoke(
        cli.app, ["plan", "free disk and check cpu/mem", "--pretty", "--no-json"])
    assert r1.exit_code == 0 and "Planned Runbook" in r1.stdout and "free_disk" in r1.stdout
    r2 = runner.invoke(
        cli.app, ["call", "rm -rf / --no-preserve-root", "--pretty", "--no-json"])
    assert r2.exit_code == 0 and "REFUSED" in r2.stdout
    r3 = runner.invoke(cli.app, [
                       "do", "web server crashed, restart and verify", "--yes", "--pretty", "--no-json"])
    assert r3.exit_code == 0 and "Execution (applied)" in r3.stdout and "heal_fakesvc_8080" in r3.stdout
