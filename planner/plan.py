from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from runbooks.catalog import RUNBOOKS
from planner.llm import llm_plan


@dataclass(frozen=True)
class Step:
    name: str
    kwargs: Dict[str, Any]


def _rules_plan(q: str) -> List[Step]:
    if "web" in q and any(tok in q for tok in ("crash", "down", "restart", "verify")):
        return [Step("heal_fakesvc_8080", {})]
    if "free" in q and "disk" in q and ("cpu" in q or "mem" in q):
        return [Step("free_disk", {}), Step("check_cpu_mem", {})]
    steps: List[Step] = []
    for name in RUNBOOKS.keys():
        if name in q:
            steps.append(Step(name, {}))
    return steps


def _safe_default() -> List[Step]:
    return [Step("check_cpu_mem", {})]


def plan_actions(query: str, mode: str = "auto") -> List[Step]:
    q = (query or "").lower().strip()

    if mode in {"rules", "auto"}:
        ruled = _rules_plan(q)
        if ruled:
            return ruled

    if mode in {"llm", "auto"}:
        proposed = llm_plan(q)
        if proposed:
            return [Step(x["name"], x.get("kwargs", {})) for x in proposed]

    fallback = _rules_plan(q)
    return fallback if fallback else _safe_default()


def plan(query: str, mode: str = "auto") -> Dict[str, Any]:
    steps = plan_actions(query, mode=mode)
    primary = steps[0] if steps else None
    is_safe_default = len(steps) == 1 and steps[0].name == "check_cpu_mem"
    action = None if is_safe_default else (primary.name if primary else None)
    return {
        "action": action,
        "kwargs": (primary.kwargs if primary else None),
        "steps": [{"name": s.name, "kwargs": s.kwargs} for s in steps],
    }
