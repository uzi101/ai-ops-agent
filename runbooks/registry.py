from typing import Dict, Any

# Safe allow-list: action name -> (modal app/function) + allowed params
RUNBOOKS: Dict[str, Dict[str, Any]] = {
    "hello":            {"modal": ("ops-agent", "hello"),            "params": []},
    "install_sql":      {"modal": ("ops-agent", "install_sql"),      "params": []},
    "free_disk":        {"modal": ("ops-agent", "free_disk"),        "params": ["dry_run", "aggressive"]},
    "restart_service":  {"modal": ("ops-agent", "restart_service"),  "params": ["name"]},
}
