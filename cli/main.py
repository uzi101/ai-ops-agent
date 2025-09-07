from __future__ import annotations

import json
from typing import Any, Dict, List

import typer

# Side-effect imports populate the global registry
import runbooks.system  # noqa: F401
import runbooks.fakesvc  # noqa: F401

from planner.plan import Step, plan_actions
from runbooks.catalog import RUNBOOKS, list_actions
from utils.audit import audit_log
from utils.shell import run_shell_safe

app = typer.Typer(help="LinOps CLI")


def _steps_to_dict(steps: List[Step]) -> List[Dict[str, Any]]:
    return [{"name": s.name, "kwargs": s.kwargs} for s in steps]


@app.command("list")
def cmd_list() -> None:
    data = {"actions": list_actions()}
    typer.echo(json.dumps(data, indent=2))


@app.command("plan")
def cmd_plan(query: str) -> None:
    steps = plan_actions(query)
    plan_dict = _steps_to_dict(steps)
    audit_log(event="plan", query=query, plan=plan_dict)
    typer.echo(json.dumps({"plan": plan_dict}, indent=2))


@app.command("do")
def cmd_do(
    query: str,
    yes: bool = typer.Option(
        False, "--yes", help="Execute (mutations). Omit to dry-run."),
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
        if isinstance(out, dict):
            results.append({"step": s.name, **out})
        else:
            results.append({"step": s.name, "ok": True, "result": out})
    audit_log(event="do", query=query, dry_run=dry_run, results=results)
    typer.echo(json.dumps({"dry_run": dry_run, "results": results}, indent=2))


@app.command("call")
def cmd_call(
    cmd: str,
    yes: bool = typer.Option(
        False, "--yes", help="Execute shell (mutations). Omit to dry-run."),
) -> None:
    res = run_shell_safe(cmd, dry_run=not yes)
    typer.echo(json.dumps(res, indent=2))


if __name__ == "__main__":
    app()
