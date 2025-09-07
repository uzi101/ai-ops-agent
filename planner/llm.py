from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from runbooks.catalog import RUNBOOKS
from utils.audit import audit_log

MAX_LLM_STEPS = 5


def llm_enabled() -> bool:
    flag = os.getenv("LINOPS_LLM", "0").lower() in {"1", "true", "yes"}
    has_key = bool(os.getenv("OPENAI_API_KEY")
                   or os.getenv("ANTHROPIC_API_KEY"))
    return flag and has_key


def _sanitize_steps(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for item in raw[:MAX_LLM_STEPS]:
        name = str(item.get("name", "")).strip()
        if name in RUNBOOKS and name not in seen:
            out.append({"name": name, "kwargs": dict(item.get("kwargs", {}))})
            seen.add(name)
    return out


def llm_plan(query: str) -> Optional[List[Dict[str, Any]]]:
    if not llm_enabled():
        audit_log(event="llm_plan_unconfigured", query=query)
        return None
    audit_log(event="llm_plan_skipped_placeholder", query=query)
    return None
