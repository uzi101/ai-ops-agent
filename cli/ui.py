# cli/ui.py
from __future__ import annotations
from typing import Any, Dict, List

# --- feature detection --------------------------------------------------------
_USE_RICH = False
try:
    from rich.console import Console  # type: ignore
    from rich.table import Table      # type: ignore
    from rich.panel import Panel      # type: ignore
    _USE_RICH = True
except Exception:
    _USE_RICH = False


# --- ASCII fallback -----------------------------------------------------------
def _ascii_table(title: str, headers: List[str], rows: List[List[str]]) -> str:
    cols = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            cols[i] = max(cols[i], len(str(c)))
    bar = "+".join("-" * (w + 2) for w in cols)

    def fmt(cells: List[str]) -> str:
        return "|".join(" " + str(cells[i]).ljust(cols[i]) + " " for i in range(len(cols)))
    out: List[str] = []
    if title:
        out.append(f"\n{title}")
    out.append(bar)
    out.append(fmt(headers))
    out.append(bar)
    for r in rows:
        out.append(fmt([str(x) for x in r]))
    out.append(bar)
    return "\n".join(out) + "\n"


# --- Rich render (captured to plain text so it always shows) ------------------
_console: Any = None
if _USE_RICH:
    _console = Console(force_terminal=True, soft_wrap=True)


def _rich_table(title: str, headers: List[str], rows: List[List[str]]) -> str:
    table = Table(title=title, show_header=True, show_lines=True)
    for h in headers:
        table.add_column(h)
    for r in rows:
        table.add_row(*[str(x) for x in r])
    with _console.capture() as cap:  # type: ignore[attr-defined]
        _console.print(table)        # type: ignore[attr-defined]
    return cap.get()


def _rich_panel(text: str) -> str:
    panel = Panel.fit(text)
    with _console.capture() as cap:  # type: ignore[attr-defined]
        _console.print(panel)        # type: ignore[attr-defined]
    return cap.get()


# --- unified printers ---------------------------------------------------------
def _print_table(title: str, headers: List[str], rows: List[List[str]]) -> None:
    if _USE_RICH:
        print(_rich_table(title, headers, rows), end="", flush=True)
    else:
        print(_ascii_table(title, headers, rows), end="", flush=True)


def _print_panel(text: str) -> None:
    if _USE_RICH:
        print(_rich_panel(text), end="", flush=True)
    else:
        print("\n" + text + "\n", end="", flush=True)


# --- public helpers -----------------------------------------------------------
def show_plan(plan: List[Dict[str, Any]]) -> None:
    rows: List[List[str]] = []
    for i, s in enumerate(plan, start=1):
        rows.append([str(i), s.get("name", ""),
                    repr(s.get("kwargs", {}) or {})])
    _print_table("Planned Runbook", ["#", "Step", "Args"], rows)


def show_results(results: List[Dict[str, Any]], dry_run: bool) -> None:
    title = "Execution (dry-run)" if dry_run else "Execution (applied)"
    rows: List[List[str]] = []
    for i, r in enumerate(results, start=1):
        step = r.get("step", "")
        ok = "true" if r.get("ok", True) else "false"
        mode = "preview" if dry_run or r.get("dry_run") else "exec"
        note = r.get("msg") or r.get("error") or r.get(
            "stderr", "") or r.get("stdout", "")
        rows.append([str(i), step, ok, mode, (note or "")[-120:]])
    _print_table(title, ["#", "Step", "OK", "Mode", "Note"], rows)


def show_refusal(cmd: str, reason: str) -> None:
    _print_panel(f"REFUSED\nReason: {reason}\nCommand: {cmd}")
