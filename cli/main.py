# cli/main.py
import os
import re
import json
from typing import Dict, Any, List, Optional

import typer
import modal

app = typer.Typer(help="Linux Ops Agent CLI (Modal-backed)")

# App name constants
OPS_APP = os.getenv("OPS_APP", "ops-agent")
AUTOHEAL_APP = os.getenv("AUTOHEAL_APP", "ops-agent-autoheal")

# Runbooks routed  to tje ops app
RUNBOOKS: Dict[str, Dict[str, Any]] = {
    "hello":              {"modal": (OPS_APP, "hello"),              "params": []},
    "install_sql":        {"modal": (OPS_APP, "install_sql"),        "params": []},
    "free_disk":          {"modal": (OPS_APP, "free_disk"),          "params": ["dry_run", "aggressive"]},
    "restart_service":    {"modal": (OPS_APP, "restart_service"),    "params": ["name"]},

    "install_package":    {"modal": (OPS_APP, "install_package"),    "params": ["pkg"]},
    "tail_logs":          {"modal": (OPS_APP, "tail_logs"),          "params": ["path", "lines"]},
    "check_cpu_mem":      {"modal": (OPS_APP, "check_cpu_mem"),      "params": ["top_n"]},
    "check_disk_health":  {"modal": (OPS_APP, "check_disk_health"),  "params": []},
    "fix_apt_lock":       {"modal": (OPS_APP, "fix_apt_lock"),       "params": []},
    "fix_nginx":          {"modal": (OPS_APP, "fix_nginx"),          "params": []},
    "restart_database":   {"modal": (OPS_APP, "restart_database"),   "params": ["name"]},

    "run_shell_safe":     {"modal": (OPS_APP, "run_shell_safe"),     "params": ["command", "dry_run"]},
}

# Local safety filter for fallback shell
BLOCK_PATTERNS = [
    "rm -rf", "mkfs", "dd if=", ">: /", "truncate -s", "shutdown", "reboot", "init 0",
    "userdel", "groupdel", ":(){ :|:& };:"
]


def is_locally_safe(cmd: str) -> bool:
    c = (cmd or "").lower().strip()
    return c and not any(p in c for p in BLOCK_PATTERNS)

# Modal helper


def call_modal(app_name: str, fn_name: str, **kwargs):
    fn = modal.Function.from_name(app_name, fn_name)
    return fn.remote(**kwargs)

# Heuristic deterministic planner (backup when LLM is unsure)


def deterministic_plan(text: str) -> List[Dict[str, Any]]:
    t = text.lower()
    steps: List[Dict[str, Any]] = []

    # disk space
    if ("free" in t or "cleanup" in t or "clean up" in t) and ("disk" in t or "space" in t or "storage" in t):
        steps.append({"action": "free_disk", "params": {"aggressive": True}})

    # CPU/memory check
    if "cpu" in t or "memory" in t or "mem" in t or "usage" in t or "perf" in t:
        steps.append({"action": "check_cpu_mem", "params": {"top_n": 5}})

    # nginx hints
    if "nginx" in t and ("fix" in t or "restart" in t or "crash" in t or "down" in t):
        if any(k in t for k in ["error", "log", "config", "conf", "syntax"]):
            steps.append({"action": "fix_nginx", "params": {}})
        else:
            steps.append({"action": "restart_service",
                         "params": {"name": "nginx"}})

    # instal package
    m = re.search(
        r"(install|setup|add)\s+(postgres|postgresql|nginx|redis|htop|git|jq|vim)\b", t)
    if m:
        pkg = m.group(2)
        if pkg in ("postgres", "postgresql"):
            steps.append({"action": "install_sql", "params": {}})
        else:
            steps.append({"action": "install_package", "params": {"pkg": pkg}})

    # logs
    if "log" in t and ("tail" in t or "last" in t or "show" in t):
        if "nginx" in t:
            steps.append({"action": "tail_logs", "params": {
                         "path": "/var/log/nginx/error.log", "lines": 20}})

    # database restart
    if ("restart" in t or "bounce" in t) and any(db in t for db in ["postgres", "postgresql", "redis"]):
        name = "postgresql" if "postgre" in t else (
            "redis" if "redis" in t else "")
        if name:
            steps.append({"action": "restart_database",
                         "params": {"name": name}})

    # de-duplicate while preserving order
    seen = set()
    deduped = []
    for s in steps:
        key = (s["action"], json.dumps(s["params"], sort_keys=True))
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped[:4]  # keep short chains


def deterministic_one_liner(text: str) -> Optional[str]:
    t = text.lower().strip()

    patterns = [
        # processes
        (r"(list|show|view)\s+(all\s+)?(running\s+)?process(es)?",
         "ps aux --sort=-%cpu | head -n 20"),
        (r"\bps\s+aux\b", "ps aux --sort=-%cpu | head -n 20"),
        (r"\bprocess( list|es)\b", "ps aux --sort=-%cpu | head -n 20"),

        # disk usage
        (r"(disk|storage).*(usage|space|free)|\bdf\b", "df -h"),

        # open/listening ports
        (r"(open|list|listening)\s+ports", "ss -tulpen"),

        # kernel/system info
        (r"kernel( version)?|\buname\b", "uname -a"),
        (r"\buptime\b", "uptime"),

        # env / network
        (r"(env|environment)\s*(vars|variables)", "printenv | head -n 50"),
        (r"(ip\s*(addr|address)|network\s*interfaces)", "ip -brief addr"),
    ]

    for pat, cmd in patterns:
        if re.search(pat, t):
            return cmd
    return None

# Planner (LLM) with chaining + refusal and deterministic backups


def plan_actions(text: str, max_steps: int = 4) -> Dict[str, Any]:
    """
    Planner flow:
      1) Try LLM to map to tools (chain).
      2) If nothing + not refused, try deterministic_plan() as a mild backup.
      3) If STILL nothing + not refused, try deterministic_one_liner() (offline).
      4) If still nothing and OPENAI key exists, try LLM shellizer.
    """
    tool_list = [{"name": k, "params": v["params"]}
                 for k, v in RUNBOOKS.items() if k != "run_shell_safe"]

    steps: List[Dict[str, Any]] = []
    fallback_shell = None
    refuse = False
    reason = None
    confidence = 0.0

    # First pass: LLM tries to pick tools
    if os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")

            system_rules = (
                "You route Linux ops requests to available tools. "
                "Prefer tools over shell. Only include parameters the tool expects. "
                "If the request is risky (delete data, reformat, reboot, create users, etc.) or outside scope, refuse."
            )
            user_task = f"""TOOLS = {tool_list}
USER = {text}

Return STRICT JSON ONLY:
{{
  "steps": [{{"action": "<tool_name>", "params": {{}}}}],     // 0..{max_steps} steps max
  "fallback_shell": null,
  "refuse": boolean,
  "reason": null | "<short reason>",
  "confidence": 0.0..1.0
}}

Rules:
- Prefer 1–3 steps. Chain only when necessary (e.g., install -> restart -> verify).
- Do NOT return fallback_shell in this pass; tools only or refusal.
- If unsafe/destructive, set refuse=true and reason.
- Use conservative defaults (e.g., lines=20 for tail_logs).
"""
            resp = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_rules},
                          {"role": "user", "content": user_task}],
                temperature=0,
            )
            txt = resp.choices[0].message.content.strip()
            start, end = txt.find("{"), txt.rfind("}")
            data = json.loads(txt[start:end+1]) if start != -1 else {}
            steps = data.get("steps") or []
            refuse = bool(data.get("refuse", False))
            reason = data.get("reason")
            confidence = float(data.get("confidence", 0.0))
        except Exception:
            pass  # fall through

    # Deterministic backup
    if (not steps) and (not refuse):
        det = deterministic_plan(text)
        if det:
            steps = det
            confidence = max(confidence, 0.55)

    # Deterministic one-liner
    if (not steps) and (not refuse):
        cmd = deterministic_one_liner(text)
        if cmd and is_locally_safe(cmd):
            fallback_shell = cmd
            confidence = max(confidence, 0.50)

    # LLM shellizer
    if (not steps) and (not refuse) and (fallback_shell is None) and os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY")
            shell_sys = (
                "Convert a plain-English Linux admin request into ONE safe, single-line command. "
                "Must be non-destructive (read-only or harmless). "
                "If no safe one-liner exists, return null."
            )
            shell_user = f"""USER = {text}

Return STRICT JSON ONLY:
{{
  "command": "<one-liner>" | null,
  "reason": null | "<why no safe single-line command>"
}}"""
            resp2 = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": shell_sys},
                          {"role": "user", "content": shell_user}],
                temperature=0,
            )
            txt2 = resp2.choices[0].message.content.strip()
            s2, e2 = txt2.find("{"), txt2.rfind("}")
            data2 = json.loads(txt2[s2:e2+1]) if s2 != -1 else {}
            cmd2 = (data2.get("command") or "").strip() or None
            if cmd2 and is_locally_safe(cmd2) and "\n" not in cmd2 and ";" not in cmd2:
                fallback_shell = cmd2
                confidence = max(confidence, 0.50)
        except Exception:
            pass

    return {
        "steps": steps[:max_steps],
        "fallback_shell": fallback_shell,
        "refuse": refuse,
        "reason": reason,
        "confidence": confidence,
    }


@app.command("list")
def list_cmd():
    """List available runbooks and their params."""
    for name, spec in RUNBOOKS.items():
        typer.echo(
            f"- {name}({', '.join(spec['params'])}) -> {spec['modal'][0]}::{spec['modal'][1]}")


@app.command("plan")
def plan_cmd(text: str, max_steps: int = typer.Option(4, "--max-steps")):
    """Preview what would run (no execution)."""
    plan = plan_actions(text, max_steps=max_steps)
    print(json.dumps(plan, indent=2))


@app.command("do")
def do_cmd(
    text: str,
    yes: bool = typer.Option(
        False, "--yes", help="Actually execute. Otherwise dry-run where supported."),
    json_out: bool = typer.Option(
        False, "--json", help="Print raw JSON summary of the chain results."),
    max_steps: int = typer.Option(
        4, "--max-steps", help="Planner cap on number of steps."),
):
    """
    Plan and execute a short chain of runbooks. Falls back to safe shell if suggested.
    Examples:
      ops do "free up disk"
      ops do "install and start nginx" --yes
      ops do "show last 20 lines of nginx error log"
    """
    plan = plan_actions(text, max_steps=max_steps)

    if plan.get("refuse"):
        reason = plan.get(
            "reason") or "The request was deemed unsafe or out of scope."
        typer.echo(f"Refused: {reason}")
        raise typer.Exit(2)

    steps: List[Dict[str, Any]] = plan.get("steps", []) or []
    results: List[Dict[str, Any]] = []
    executed_any = False

    for i, step in enumerate(steps[:max_steps], start=1):
        action = step.get("action")
        params = step.get("params") or {}
        if action not in RUNBOOKS:
            results.append({"step": i, "action": action,
                           "error": "unknown_action"})
            continue

        spec = RUNBOOKS[action]
        allowed = {k: v for k, v in params.items() if k in spec["params"]}
        if action == "free_disk":
            allowed["dry_run"] = not yes

        typer.echo(f"→ Step {i}: {action} {allowed}")
        try:
            out = call_modal(*spec["modal"], **allowed)
            executed_any = True
            results.append({"step": i, "action": action, "result": out})
        except Exception as e:
            results.append({"step": i, "action": action, "error": str(e)})
            break  # stop chain on failure

    # Safe shell fallback only if nothing executed and planner suggested one
    if not executed_any and plan.get("fallback_shell"):
        shell_cmd = plan["fallback_shell"]
        if not is_locally_safe(shell_cmd):
            typer.echo("Planner proposed an unsafe shell command. Aborting.")
            raise typer.Exit(3)
        spec = RUNBOOKS["run_shell_safe"]
        dry_run = not yes
        typer.echo(f"→ Fallback shell: {shell_cmd} (dry_run={dry_run})")
        out = call_modal(*spec["modal"], command=shell_cmd, dry_run=dry_run)
        results.append({"fallback_shell": shell_cmd, "result": out})

    summary = {
        "input": text,
        "confidence": plan.get("confidence", 0.0),
        "steps": steps,
        "executed": results,
        "used_fallback": bool(not executed_any and plan.get("fallback_shell")),
    }

    if json_out:
        print(json.dumps(summary, indent=2))
    else:
        typer.echo(f"Plan confidence: {summary['confidence']:.2f}")
        for item in results:
            label = f"step {item['step']}: {item.get('action')}" if "step" in item else "fallback_shell"
            if "error" in item:
                typer.echo(f"{label} → ERROR: {item['error']}")
            else:
                payload = item.get("result")
                pretty = json.dumps(payload, indent=2) if isinstance(
                    payload, (dict, list)) else str(payload)
                typer.echo(f"{label} →\n{pretty}")


@app.command("direct")
def direct_cmd(
    action: str,
    param: List[str] = typer.Option(
        None, "--param", help="key=value (repeatable)"),
    yes: bool = typer.Option(
        False, "--yes", help="Execute (respects dry_run where supported)"),
):
    """Call a runbook directly without the LLM (handy for demos/tests)."""
    if action not in RUNBOOKS:
        typer.echo(f"Unknown action '{action}'. Try 'ops list'.")
        raise typer.Exit(2)

    spec = RUNBOOKS[action]
    provided: Dict[str, Any] = {}
    for p in param or []:
        if "=" in p:
            k, v = p.split("=", 1)
            provided[k] = v

    allowed = {k: v for k, v in provided.items() if k in spec["params"]}
    if action == "free_disk":
        allowed["dry_run"] = not yes

    typer.echo(f"→ Direct: {action} {allowed}")
    out = call_modal(*spec["modal"], **allowed)
    pretty = json.dumps(out, indent=2) if isinstance(
        out, (dict, list)) else str(out)
    print(pretty)


@app.command("health")
def health_cmd(json_out: bool = typer.Option(True, "--json/--no-json", help="Print JSON")):
    """Run a single auto-heal pass and print the JSON summary."""
    fn = modal.Function.from_name(AUTOHEAL_APP, "watch_once")
    result = fn.remote()
    print(json.dumps(result, indent=2) if json_out else str(result))


if __name__ == "__main__":
    app()
