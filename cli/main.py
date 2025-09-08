from __future__ import annotations

import json
from typing import Any, Dict, List

import typer

# populate registry
import runbooks.system  # noqa: F401
import runbooks.fakesvc  # noqa: F401

from planner.plan import Step, plan_actions
from runbooks.catalog import RUNBOOKS, list_actions
from utils.audit import audit_log
from utils.shell import run_shell_safe

# NEW: import UI
from cli.ui import show_plan, show_results, show_refusal

app = typer.Typer(help="Grep CLI")


def _steps_to_dict(steps: List[Step]) -> List[Dict[str, Any]]:
    return [{"name": s.name, "kwargs": s.kwargs} for s in steps]


@app.command("list")
def cmd_list() -> None:
    data = {"actions": list_actions()}
    typer.echo(json.dumps(data, indent=2))


@app.command("plan")
def cmd_plan(
    query: str,
    pretty: bool = typer.Option(False, "--pretty/--no-pretty"),
    json_out: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    steps = plan_actions(query)
    plan_dict = _steps_to_dict(steps)
    audit_log(event="plan", query=query, plan=plan_dict)
    if pretty:
        show_plan(plan_dict)
    if json_out and not pretty:
        typer.echo(json.dumps({"plan": plan_dict}, indent=2))


@app.command("do")
def cmd_do(
    query: str,
    yes: bool = typer.Option(
        False, "--yes", help="Execute (otherwise dry-run)."),
    pretty: bool = typer.Option(False, "--pretty/--no-pretty"),
    json_out: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    dry_run = not yes
    steps = plan_actions(query)
    results: List[Dict[str, Any]] = []
    for s in steps:
        fn = RUNBOOKS.get(s.name)
        if not fn:
            results.append({"step": s.name, "ok": False,
                           "error": "unknown_action"})
            continue
        out = fn(dry_run=dry_run, **s.kwargs)
        results.append(
            {"step": s.name, **(out if isinstance(out, dict) else {"ok": True})})
    audit_log(event="do", query=query, dry_run=dry_run, results=results)
    if pretty:
        show_results(results, dry_run=dry_run)
    if json_out and not pretty:
        typer.echo(json.dumps(
            {"dry_run": dry_run, "results": results}, indent=2))


@app.command("call")
def cmd_call(
    cmd: str,
    yes: bool = typer.Option(
        False, "--yes", help="Execute shell (otherwise dry-run)."),
    pretty: bool = typer.Option(False, "--pretty/--no-pretty"),
    json_out: bool = typer.Option(True, "--json/--no-json"),
) -> None:
    res = run_shell_safe(cmd, dry_run=not yes)
    if pretty and res.get("refused"):
        show_refusal(cmd, res.get("reason", "unsafe"))
        return
    if json_out and not pretty:
        typer.echo(json.dumps(res, indent=2))
