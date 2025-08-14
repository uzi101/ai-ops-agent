import json
import os
import subprocess
from typing import List, Dict, Any

import modal

OPS_APP = os.getenv("OPS_APP", "ops-agent")

# This file itself is a small Modal app containing two functions:
# - watch_once(): run one health check + healing pass and return JSON
# - watch_scheduled(): run the same pass on a cron schedule
app = modal.App("ops-agent-autoheal")

# Config (can be overridden per run/deploy via env)
DISK_THRESHOLD = int(os.getenv("DISK_THRESHOLD", "85")
                     )     # % usage to trigger cleanup
WATCH_SERVICES: List[str] = [s.strip() for s in os.getenv(
    "WATCH_SERVICES", "nginx").split(",") if s.strip()]
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes")

image = (
    modal.Image.debian_slim()
    .apt_install("procps")
)

# helpers


def _shell(cmd: str) -> subprocess.CompletedProcess[str]:
    """Run a shell command, capture output; never raise on non-zero exit."""
    return subprocess.run(["bash", "-lc", cmd], text=True, capture_output=True, check=False)


def _call_ops(fn_name: str, **kwargs):
    """
    Call a function that lives in another deployed Modal app (OPS_APP).
    We use Function.from_name(...).remote(...) which works in Modal 1.x.
    """
    fn = modal.Function.from_name(OPS_APP, fn_name)
    return fn.remote(**kwargs)


def _disk_used_percent() -> int:
    """Return root (/) disk usage percent as int (real reading inside this container)."""
    out = _shell(
        r"df -P / | tail -1 | awk '{print $5}' | tr -d '%'").stdout.strip()
    return int(out or "0")


def _service_running_exact(name: str) -> bool:
    """True if a process with exact name exists (no systemd required)."""
    return _shell(f"pgrep -x {name} >/dev/null 2>&1 && echo RUNNING || true").stdout.strip() == "RUNNING"


def _check_disk_and_maybe_heal() -> Dict[str, Any]:
    pct = _disk_used_percent()
    action = None
    healed = False

    if pct >= DISK_THRESHOLD:
        action = f"free_disk(aggressive=True, dry_run={DRY_RUN})"
        if not DRY_RUN:
            _call_ops("free_disk", aggressive=True, dry_run=False)
            healed = True

    return {
        "metric": "disk_used_percent",
        "value": pct,
        "threshold": DISK_THRESHOLD,
        "action": action,
        "healed": healed,
    }


def _check_services_and_maybe_heal() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for svc in WATCH_SERVICES:
        running = _service_running_exact(svc)
        action = None
        healed = False

        if not running:
            action = f"restart_service(name={svc})"
            if not DRY_RUN:
                res = _call_ops("restart_service", name=svc)
                healed = True
                # if the runbook returned a short string/json, attach a tiny preview
                if isinstance(res, str) and res:
                    action += f" -> {res[:120]}"

        results.append({
            "service": svc,
            "running": running,
            "action": action,
            "healed": healed
        })
    return results


def _watch_impl() -> Dict[str, Any]:
    disk = _check_disk_and_maybe_heal()
    services = _check_services_and_maybe_heal()
    return {"disk": disk, "services": services, "dry_run": DRY_RUN}

# Modal functions


@app.function(image=image, timeout=120)
def watch_once() -> Dict[str, Any]:
    """
    One pass of auto-heal:
      - read real disk %; if >= threshold, trigger free_disk (unless DRY_RUN)
      - for each WATCH_SERVICES entry, if not running, trigger restart_service (unless DRY_RUN)
    Returns a JSON summary and prints it so you see it in the Modal run logs.
    """
    summary = _watch_impl()
    print(json.dumps(summary, indent=2))
    return summary

# Every 5 minutes via cron on Modal


@app.function(image=image, timeout=120, schedule=modal.Cron("*/5 * * * *"))
def watch_scheduled() -> Dict[str, Any]:
    summary = _watch_impl()
    print(json.dumps(summary, indent=2))
    return summary


@app.local_entrypoint()
def main():
    print(watch_once.remote())
