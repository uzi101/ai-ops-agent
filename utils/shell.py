# Safely run shell commands with audit + refusals + dry-run-by-default.

import subprocess
from typing import Optional, Tuple
from utils.audit import audit_log

# Don't allow these commands
BLOCKLIST = [
    "rm -rf /",
    "--no-preserve-root",
    "mkfs",
    ":(){ :|:& };:",
    "dd if=/dev/zero of=/dev/sd",
    "shutdown", "reboot", "cryptsetup"
]


def is_safe_command(cmd: str) -> Tuple[bool, Optional[str]]:
    """
    Decide if a command is obviously unsafe based on BLOCKLIST.
    Returns (ok, reason).
      - ok=True: command passes this basic screen
      - ok=False: refused, and 'reason' describes why
    NOTE: This is a *first line* of defense. We'll add allowlists/policies later.
    """
    low = (cmd or "").lower().strip()
    for bad in BLOCKLIST:
        if bad in low:
            return False, f"blocked token: {bad}"
    return True, None


def run_shell_safe(cmd: str, dry_run: bool = True, timeout: int = 60, cwd: str | None = None):
    """
    Execute a shell command in a safety-first, auditable way.

    Behaviors:
      - If the command hits BLOCKLIST => REFUSE and audit an event {event:'refusal', ...}
      - If dry_run=True (default)     => DON'T execute; audit {event:'shell_dry_run', ...}
      - Else                          => Execute via subprocess, capture output, audit {event:'shell_exec', ...}

    Returns a small dict describing the result. We keep it simple + JSON-serializable.
    """
    ok, reason = is_safe_command(cmd)
    if not ok:
        # 2) Refusal path
        audit_log(event="refusal", cmd=cmd, reason=reason)
        return {"ok": False, "refused": True, "reason": reason, "cmd": cmd}

    if dry_run:
        # 3) Dry-run path
        audit_log(event="shell_dry_run", cmd=cmd)
        return {"ok": True, "dry_run": True, "cmd": cmd}

    # 4) Real execution path
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout
    )
    out = {
        "ok": proc.returncode == 0,
        "rc": proc.returncode,
        # We "tail" the outputs so logs stay readable
        "stdout": (proc.stdout or "")[-2000:],
        "stderr": (proc.stderr or "")[-2000:],
        "cmd": cmd,
    }
    # 5) Always audit real executions
    audit_log(event="shell_exec", **out)
    return out
