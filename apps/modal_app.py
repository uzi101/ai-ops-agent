# apps/modal_app.py
import os
import re
import json
import subprocess
from typing import Optional, List, Dict, Any

import modal

app = modal.App("ops-agent")

image = (
    modal.Image.debian_slim()
    .apt_install(
        "curl",
        "procps",
        "util-linux",
        "gzip",
        "tar",
        "jq",
        "nginx"
    )
)

# shell helpers


def sh(cmd: str) -> dict:
    """Run a shell command; return {rc, out_tail} for logs/UI."""
    env = os.environ.copy()
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "HOME": "/root",
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "UMASK": "077",
        }
    )
    p = subprocess.run(
        ["bash", "-lc", cmd],
        text=True,
        capture_output=True,
        env=env,
    )
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    tail = out[-2000:] if out else ""
    return {"rc": p.returncode, "out_tail": tail}


def with_cmd(cmd: str, res: Dict[str, Any]) -> Dict[str, Any]:
    """Attach the command to its result for consistent logs."""
    return {"cmd": cmd, **res}


# Existing basics

@app.function(image=image)
def hello() -> str:
    return "Hello from Modal 👋 (Linux container)."


@app.function(image=image)
def install_sql() -> str:
    cmds = [
        "apt-get update -y",
        "DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql postgresql-contrib",
        "psql --version || true",
    ]
    logs = [sh(c) for c in cmds]
    return "PostgreSQL installed.\n" + json.dumps(logs[-1], indent=2)


@app.function(image=image)
def free_disk(dry_run: bool = True, aggressive: bool = False) -> dict:
    """Free disk space; return bytes reclaimed estimate (best effort)."""
    before = sh("df -P --output=used / | tail -1").get("out_tail", "0").strip()
    ops = []
    ops.append("apt-get clean")
    ops.append("rm -rf /var/cache/apt/archives/* || true")
    ops.append("journalctl --vacuum-time=1d || true")
    ops.append("find /var/log -type f -name '*.log' -size +5M -delete || true")
    if aggressive:
        ops.append(
            "find /tmp -mindepth 1 -maxdepth 1 -type f -mtime +1 -delete || true")
        ops.append(
            "find /var/tmp -mindepth 1 -maxdepth 1 -type f -mtime +1 -delete || true")
    if dry_run:
        return {"dry_run": True, "would_run": ops}
    for c in ops:
        sh(c)
    after = sh("df -P --output=used / | tail -1").get("out_tail", "0").strip()
    return {"dry_run": False, "steps": ops, "before_used": before, "after_used": after}


@app.function(image=image)
def restart_service(name: str) -> dict:
    """
    Try multiple restart mechanisms, then verify with pgrep.
    For nginx, also verify HTTP 200 on localhost.
    """
    steps: List[Dict[str, Any]] = []

    def runstep(cmd: str):
        res = sh(cmd)
        steps.append(with_cmd(cmd, res))
        return res

    # 1) Try systemd, SysV, OpenRC restart
    runstep(f"systemctl restart {name} || true")
    runstep(f"sudo systemctl restart {name} || true")
    runstep(f"service {name} restart || true")
    runstep(f"sudo service {name} restart || true")
    runstep(f"rc-service {name} restart || true")

    # 2) Verify process; if not running, try explicit start paths
    running_rc = runstep(
        f"pgrep -x {name} >/dev/null 2>&1; echo $?")["out_tail"].strip()
    is_running = running_rc.endswith("0")

    if not is_running:
        runstep(f"systemctl start {name} || true")
        runstep(f"sudo systemctl start {name} || true")
        runstep(f"service {name} start || true")
        runstep(f"sudo service {name} start || true")
        runstep(f"rc-service {name} start || true")

        # Last-resort: direct launcher
        if name == "nginx":
            runstep(
                r"( command -v nginx >/dev/null 2>&1 && nohup nginx >/dev/null 2>&1 & ) || true")
        else:
            runstep(
                rf"( command -v {name} >/dev/null 2>&1 && nohup {name} >/dev/null 2>&1 & ) || true")

        # Recheck
        running_rc = runstep(
            f"pgrep -x {name} >/dev/null 2>&1; echo $?")["out_tail"].strip()
        is_running = running_rc.endswith("0")

    http_ok = False
    if name == "nginx" and is_running:
        http_code = runstep(
            "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true")["out_tail"].strip()
        http_ok = (http_code == "200")

    ok = is_running and (http_ok if name == "nginx" else True)
    return {
        "ok": ok,
        "verified_running": is_running,
        "http_ok": http_ok if name == "nginx" else None,
        "steps": steps,
    }


# runbooks

@app.function(image=image)
def install_package(pkg: str) -> dict:
    """Generic apt install with minimal allowlist for safety."""
    ALLOW = {
        "nginx", "postgresql", "postgresql-contrib",
        "redis", "htop", "curl", "vim", "jq", "python3", "git",
        "mysql-server", "mariadb-server"
    }
    if pkg not in ALLOW:
        return {"ok": False, "reason": f"'{pkg}' not in allowlist", "allow": sorted(ALLOW)}
    steps = [
        with_cmd("apt-get update -y", sh("apt-get update -y")),
        with_cmd(f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg}",
                 sh(f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg}")),
        with_cmd(f"{pkg} --version || which {pkg} || true",
                 sh(f"{pkg} --version || which {pkg} || true")),
    ]
    return {"ok": True, "pkg": pkg, "steps": steps}


@app.function(image=image)
def tail_logs(path: str, lines: int = 50) -> dict:
    """Return last N lines from a file in safe paths."""
    SAFE_PREFIXES = ("/var/log", "/tmp", "/var/tmp")
    if not any(path.startswith(p) for p in SAFE_PREFIXES):
        return {"ok": False, "reason": "path not allowed", "safe_prefixes": SAFE_PREFIXES}
    res = sh(f"tail -n {int(lines)} {path} || true")
    redacted = res["out_tail"].replace(
        "password", "******").replace("secret", "******")
    return {"ok": True, "path": path, "lines": lines, "content_tail": redacted}


@app.function(image=image)
def check_cpu_mem(top_n: int = 5) -> dict:
    """
    Robust CPU/mem snapshot for short-lived containers:
    - CPU: sample /proc/stat twice and compute delta usage %
    - Mem: parse /proc/meminfo (kB) -> MB integers
    - Top: ps aux (top N by CPU)
    """
    def read_proc_stat():
        out = sh("cat /proc/stat | head -n 1")["out_tail"].strip()
        parts = out.split()
        if len(parts) < 8 or parts[0] != "cpu":
            return None
        try:
            vals = list(map(int, parts[1:8]))
            idle = vals[3] + vals[4]
            total = sum(vals)
            return total, idle
        except Exception:
            return None

    s1 = read_proc_stat()
    sh("sleep 0.2")  # keep tiny for Modal speed
    s2 = read_proc_stat()

    cpu_percent = 0
    if s1 and s2:
        total1, idle1 = s1
        total2, idle2 = s2
        d_total = max(1, total2 - total1)
        d_idle = max(0, idle2 - idle1)
        used = max(0, d_total - d_idle)
        cpu_percent = int((used * 100) / d_total)

    meminfo = sh("cat /proc/meminfo | sed -n '1,5p'")["out_tail"]
    mem_total_kb = 0
    mem_available_kb = 0
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            try:
                mem_total_kb = int(line.split()[1])
            except Exception:
                pass
        elif line.startswith("MemAvailable:"):
            try:
                mem_available_kb = int(line.split()[1])
            except Exception:
                pass
    mem_used_mb = 0
    mem_total_mb = 0
    if mem_total_kb > 0:
        mem_total_mb = mem_total_kb // 1024
        mem_used_mb = max(0, (mem_total_kb - mem_available_kb) // 1024)

    top_n = max(1, int(top_n))
    top_out = sh(f"ps aux --sort=-%cpu | head -n {top_n + 1}")["out_tail"]

    return {
        "cpu_percent": int(cpu_percent),
        "mem_used_mb": int(mem_used_mb),
        "mem_total_mb": int(mem_total_mb),
        "top": top_out,
    }


@app.function(image=image)
def fix_apt_lock() -> dict:
    """Common apt/dpkg lock fix sequence."""
    steps = [
        with_cmd("fuser -vki /var/lib/dpkg/lock-frontend || true",
                 sh("fuser -vki /var/lib/dpkg/lock-frontend || true")),
        with_cmd("dpkg --configure -a || true",
                 sh("dpkg --configure -a || true")),
        with_cmd("apt-get -f install -y || true",
                 sh("apt-get -f install -y || true")),
        with_cmd("rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock || true",
                 sh("rm -f /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock || true")),
        with_cmd("apt-get update -y || true", sh("apt-get update -y || true")),
    ]
    return {"ok": True, "steps": steps}


@app.function(image=image)
def fix_nginx() -> dict:
    """Diagnose nginx: config test, error log tail, restart, verify port 80."""
    diag = [
        with_cmd("nginx -t || true", sh("nginx -t || true")),
        with_cmd("tail -n 50 /var/log/nginx/error.log || true",
                 sh("tail -n 50 /var/log/nginx/error.log || true")),
        with_cmd("systemctl restart nginx || service nginx restart || true",
                 sh("systemctl restart nginx || service nginx restart || true")),
        with_cmd("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true",
                 sh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ || true")),
    ]
    syntax_ok = any("syntax is ok" in d["out_tail"].lower() for d in diag)
    http_ok = "200" in diag[-1]["out_tail"]
    return {"ok": bool(syntax_ok and http_ok), "http_ok": http_ok, "steps": diag}

# Disk health diagnostics


@app.function(image=image, timeout=180)
def check_disk_health(max_paths: int = 10) -> Dict[str, Any]:
    """
    Summarizes disk usage:
      - partition usage (mountpoint + percent used)
      - top N heavyweight paths on root filesystem (bytes, path)
    """
    steps: List[Dict[str, Any]] = []

    part = with_cmd(r"df -P | awk 'NR>1 {gsub(\"%\", \"\", $5); print $6\" \"$5}'", sh(
        r"df -P | awk 'NR>1 {gsub(\"%\", \"\", $5); print $6\" \"$5}'"))
    steps.append(part)
    partitions: List[Dict[str, Any]] = []
    if part["rc"] == 0:
        for line in (part["out_tail"] or "").splitlines():
            try:
                mount, pct = line.rsplit(" ", 1)
                partitions.append(
                    {"mount": mount.strip(), "used_percent": int(pct)})
            except Exception:
                pass

    heavy = with_cmd(f"du -x -b -d1 / 2>/dev/null | sort -nr | head -n {int(max_paths)}",
                     sh(f"du -x -b -d1 / 2>/dev/null | sort -nr | head -n {int(max_paths)}"))
    steps.append(heavy)
    top_paths: List[Dict[str, Any]] = []
    if heavy["rc"] == 0:
        for line in (heavy["out_tail"] or "").splitlines():
            try:
                size_str, path = line.strip().split("\t", 1)
                top_paths.append({"bytes": int(size_str), "path": path})
            except Exception:
                pass

    return {"ok": True, "partitions": partitions, "top_paths": top_paths, "steps": steps, "notes": "check_disk_health"}

# Restart database with verification


@app.function(image=image, timeout=240)
def restart_database(name: str = "postgres") -> Dict[str, Any]:
    """
    Attempts to restart a database service and verifies with pgrep.
    name may be: "postgres", "postgresql", "mysql", "mariadb".
    """
    steps: List[Dict[str, Any]] = []

    name_l = name.lower()
    if name_l in ("postgres", "postgresql"):
        service_candidates = ["postgresql", "postgres"]
        pgrep_candidates = ["postgres", "postmaster"]
    elif name_l in ("mysql", "mariadb"):
        service_candidates = ["mysql", "mariadb"]
        pgrep_candidates = ["mysqld", "mariadbd"]
    else:
        service_candidates = [name_l]
        pgrep_candidates = [name_l]

    for svc in service_candidates:
        steps.append(with_cmd(f"systemctl restart {svc} || sudo systemctl restart {svc}", sh(
            f"systemctl restart {svc} || sudo systemctl restart {svc}")))
        if steps[-1]["rc"] == 0:
            break
        steps.append(with_cmd(f"service {svc} restart || sudo service {svc} restart", sh(
            f"service {svc} restart || sudo service {svc} restart")))
        if steps[-1]["rc"] == 0:
            break
        steps.append(with_cmd(
            f"rc-service {svc} restart || true", sh(f"rc-service {svc} restart || true")))

    if pgrep_candidates:
        kill_cmd = " || ".join(
            [f"pkill -x {p} || true" for p in pgrep_candidates])
        steps.append(with_cmd(kill_cmd, sh(kill_cmd)))

    verify_cmd = " || ".join(
        [f"pgrep -x {p}" for p in pgrep_candidates]) + " >/dev/null 2>&1; echo $?"
    verify = with_cmd(verify_cmd, sh(verify_cmd))
    steps.append(verify)
    verified_running = verify["out_tail"].strip().endswith("0")

    ok = verified_running
    return {
        "ok": ok,
        "verified_running": verified_running,
        "detected": {"service_names": service_candidates, "pgrep_names": pgrep_candidates},
        "steps": steps,
        "notes": f"restart_database({name})",
    }

# Safety: generic safe shell (single & multi)


# Stronger blocklist for obviously dangerous operations.
# (Heuristic: simple substring checks; we’re not a shell parser.)
BLOCK_PATTERNS = [
    " rm -rf", " rm -r /", " rm -rf /", " rm -rf /*",  # destructive delete
    " mkfs", " mkfs.", " mke2fs", " mkfs.ext",         # reformat
    " dd if=", " dd of=/dev/", " of=/dev/sd",          # raw disk writes
    " wipefs", " cryptsetup", " luksformat",           # disk wipe/encrypt
    " fdisk", " parted", " sfdisk",                    # partition editors
    " :(){ :|:& };:",                                  # fork bomb
    " shutdown", " poweroff", " halt", " init 0",      # power control
    " reboot", " init 6",
    " chown -R /", " chmod -R /",                      # perms on root
    " >/dev/sd", " >>/dev/sd",                         # redirects to disks
    " >/dev/nvme", " >>/dev/nvme",
    " >/dev/mmcblk", " >>/dev/mmcblk",
]

# Writes are allowed only into these prefixes
SAFE_WRITE_PREFIXES = ("/tmp", "/var/tmp", "/var/log")

# Some commands we consider read-only (best-effort heuristic)
READONLY_BIN = (
    "cat", "grep", "egrep", "zgrep", "head", "tail", "sed", "awk", "cut",
    "wc", "ls", "stat", "df", "du", "mount", "uname", "whoami", "id",
    "ps", "top", "free", "uptime", "date", "hostname", "env", "printenv",
)

_redir_re = re.compile(r"(^|[^\\])\s([>|]>{0,1})\s*(\S+)")
_rm_root_re = re.compile(r"\brm\s+-rf?\s+/(?:\s|$)")
_cmd_name_re = re.compile(r"^\s*([a-zA-Z0-9._-]+)")


def _has_blocked_pattern(cmd: str) -> Optional[str]:
    low = f" {cmd.strip().lower()} "
    for pat in BLOCK_PATTERNS:
        if pat in low:
            return f"blocked by pattern: {pat.strip()}"
    # Special case: rm -rf /
    if _rm_root_re.search(cmd):
        return "blocked dangerous delete of /"
    return None


def _safe_write_targets(cmd: str) -> Optional[str]:
    """
    If the command contains a redirection (> or >>), ensure the target path
    lives under SAFE_WRITE_PREFIXES. Return reason if unsafe, else None.
    """
    for m in _redir_re.finditer(cmd):
        target = m.group(3)
        target = target.strip().strip("'").strip('"')
        if target.startswith(">"):  # weird parse, skip
            continue
        # Only absolute paths considered; relative paths allowed (treated as cwd)
        if target.startswith("/"):
            if not any(target.startswith(p) for p in SAFE_WRITE_PREFIXES):
                return f"write outside safe paths: {target}"
    return None


def _seems_readonly(cmd: str) -> bool:
    m = _cmd_name_re.match(cmd)
    if not m:
        return False
    exe = m.group(1)
    return exe in READONLY_BIN


def is_safe_command(cmd: str) -> (bool, Optional[str]):
    """
    Heuristic safety:
      - deny if any blocked pattern
      - deny if redirection target outside SAFE_WRITE_PREFIXES
      - allow read-only commands liberally
      - otherwise allow (since we also run inside container)
    """
    if not cmd or not cmd.strip():
        return False, "empty command"
    reason = _has_blocked_pattern(cmd)
    if reason:
        return False, reason
    redir_reason = _safe_write_targets(cmd)
    if redir_reason:
        return False, redir_reason
    # Optionally add more granular checks
    return True, None


@app.function(image=image)
def run_shell_safe(command: str, dry_run: bool = True) -> dict:
    """
    Execute a *single* shell command if it passes a simple safety filter.
    Backstop for LLM-routed unknown requests.
    """
    ok, reason = is_safe_command(command)
    if not ok:
        return {"ok": False, "reason": reason, "command": command}
    if dry_run:
        return {"ok": True, "dry_run": True, "command": command}
    res = sh(command)
    return {"ok": res["rc"] == 0, "dry_run": False, "command": command, "result": res}


@app.function(image=image)
def run_shell_script(commands: List[str], dry_run: bool = True, stop_on_error: bool = True) -> dict:
    """
    Execute a short list of shell commands with basic safety checks per line.
    - If *any* command is unsafe, default behavior is to stop before executing (dry-run or real),
      returning the blocked reason. If stop_on_error=False, we will skip only the unsafe ones.
    """
    if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
        return {"ok": False, "reason": "commands must be a list[str]"}

    plan: List[Dict[str, Any]] = []
    unsafe_found = False

    # Safety & planning pass
    for idx, cmd in enumerate(commands, start=1):
        ok, reason = is_safe_command(cmd)
        plan.append({"index": idx, "cmd": cmd,
                    "safe": ok, "blocked_reason": reason})
        if not ok:
            unsafe_found = True
            if stop_on_error:
                break

    if unsafe_found and stop_on_error:
        return {
            "ok": False,
            "dry_run": True,  # nothing executed
            "stopped_at": len(plan),
            "plan": plan,
            "reason": "unsafe command present; execution halted",
        }

    # Execute (or dry-run)
    results: List[Dict[str, Any]] = []
    executed_any = False
    if dry_run:
        for p in plan:
            if p["safe"]:
                results.append(
                    {"index": p["index"], "cmd": p["cmd"], "dry_run": True})
            else:
                results.append({"index": p["index"], "cmd": p["cmd"],
                               "skipped": True, "blocked_reason": p["blocked_reason"]})
        return {"ok": not unsafe_found, "dry_run": True, "plan": plan, "results": results}

    # real execution
    for p in plan:
        if not p["safe"]:
            results.append({"index": p["index"], "cmd": p["cmd"],
                           "skipped": True, "blocked_reason": p["blocked_reason"]})
            if stop_on_error:
                break
            continue
        executed_any = True
        res = sh(p["cmd"])
        results.append({"index": p["index"], "cmd": p["cmd"],
                       "rc": res["rc"], "out_tail": res["out_tail"]})
        if res["rc"] != 0 and stop_on_error:
            break

    ok = (not unsafe_found) and all(r.get("rc", 0)
                                    == 0 or r.get("skipped") for r in results)
    return {"ok": ok, "dry_run": False, "plan": plan, "results": results}
