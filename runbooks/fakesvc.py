from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from typing import Any, Dict

from runbooks.catalog import register
from utils.audit import audit_log

DEFAULT_PORT = 8080
DEFAULT_PIDFILE = "/tmp/fakesvc.pid"


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _wait_port(port: int, timeout_s: float = 2.0, interval_s: float = 0.05) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _port_open(port):
            return True
        time.sleep(interval_s)
    return _port_open(port)


def _start_http_server(port: int, pidfile: str) -> Dict[str, Any]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        with open(pidfile, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except Exception as e:
        return {"ok": False, "error": f"pidfile_write_failed: {e!r}", "port": port}
    audit_log(event="spawn_proc", cmd=[
              sys.executable, "-m", "http.server", str(port)], pid=proc.pid, port=port)
    return {"ok": True, "pid": proc.pid, "port": port}


@register("heal_fakesvc_8080")
def heal_fakesvc_8080(
    dry_run: bool = True,
    port: int = DEFAULT_PORT,
    pidfile: str = DEFAULT_PIDFILE,
) -> Dict[str, Any]:
    if _port_open(port):
        return {"ok": True, "msg": "service healthy", "port": port}
    if dry_run:
        return {
            "ok": False,
            "verify": {"ok": False, "port": port},
            "would_start": {"cmd": [sys.executable, "-m", "http.server", str(port)], "pidfile": pidfile},
        }
    start = _start_http_server(port, pidfile)
    if not start.get("ok"):
        return {"ok": False, "start": start, "verify": {"ok": False, "port": port}}
    verify_ok = _wait_port(port)
    return {"ok": bool(start.get("ok")) and verify_ok, "start": start, "verify": {"ok": verify_ok, "port": port}}
