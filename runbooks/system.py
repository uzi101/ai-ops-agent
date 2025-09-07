from __future__ import annotations

import os
import platform
from typing import Any, Dict, List

from runbooks.catalog import register
from utils.shell import run_shell_safe

DEFAULT_MOUNT = "/"
DEFAULT_FILLFILE = "/tmp/linops_fillfile"


@register("free_disk")
def free_disk(dry_run: bool = True, mount: str = DEFAULT_MOUNT, fillfile: str = DEFAULT_FILLFILE) -> Dict[str, Any]:
    """
    Free space in a demo-safe way and report disk usage.
    - If a known temp file exists, remove it.
    - Always report disk usage for the chosen mount.
    """
    actions: List[Dict[str, Any]] = []
    if os.path.exists(fillfile):
        actions.append(run_shell_safe(f"rm -f {fillfile}", dry_run=dry_run))
    actions.append(run_shell_safe(f"df -h {mount}", dry_run=True))
    return {"ok": True, "actions": actions, "mount": mount}


@register("check_cpu_mem")
def check_cpu_mem(dry_run: bool = True) -> Dict[str, Any]:
    """
    Cross-platform snapshot of load and memory state.
    Uses commands that exist on macOS (Darwin) and Linux without root.
    """
    sys = platform.system().lower()
    cmds: List[str] = ["uptime"]
    if sys == "darwin":
        cmds.append("vm_stat")
    else:
        cmds.append("free -h || head -n 10 /proc/meminfo")
    checks = [run_shell_safe(c, dry_run=True) for c in cmds]
    return {"ok": True, "checks": checks, "os": sys}
