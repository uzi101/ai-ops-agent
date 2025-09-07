import json
from typer.testing import CliRunner
import cli.main as cli

runner = CliRunner()


def test_list_actions_ok():
    r = runner.invoke(cli.app, ["list"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert "actions" in data and isinstance(data["actions"], list)


def test_plan_maps_demo_phrase():
    r = runner.invoke(cli.app, ["plan", "free disk and check cpu/mem"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data["plan"][0]["name"] == "free_disk"


def test_call_refuses_unsafe():
    r = runner.invoke(cli.app, ["call", "rm -rf / --no-preserve-root"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert data.get("refused") is True


def test_do_is_dry_run_by_default():
    r = runner.invoke(cli.app, ["do", "free disk and check cpu/mem"])
    data = json.loads(r.stdout)
    assert data["dry_run"] is True
    assert len(data["results"]) >= 1
