import os
import re
import json
from typing import Dict, Any
from runbooks.registry import RUNBOOKS


def _rules(text: str) -> Dict[str, Any]:
    t = text.lower()
    if ("install" in t) and any(k in t for k in ["postgres", "postgresql", "psql", "sql"]):
        return {"action": "install_sql", "params": {}, "confidence": 0.6}
    if ("free" in t and "disk" in t) or ("clear" in t and "space" in t):
        aggressive = "aggressive" in t or "everything" in t
        return {"action": "free_disk", "params": {"dry_run": True, "aggressive": aggressive}, "confidence": 0.6}
    if "nginx" in t and any(k in t for k in ["restart", "fix", "crash", "crashed", "down"]):
        return {"action": "restart_service", "params": {"name": "nginx"}, "confidence": 0.6}
    m = re.search(r"restart\s+([a-z0-9\-\.]+)", t)
    if m:
        return {"action": "restart_service", "params": {"name": m.group(1)}, "confidence": 0.5}
    return {"action": None, "params": {}, "confidence": 0.0, "reason": "No safe runbook matched"}


def plan(text: str) -> Dict[str, Any]:
    """LLM router constrained to RUNBOOKS; falls back to rules if no OPENAI_API_KEY."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _rules(text)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        tools = [{"name": k, "params": RUNBOOKS[k]["params"]}
                 for k in RUNBOOKS]
        prompt = f"""
You are a router. Allowed actions: {tools}
User: {text}
Return STRICT JSON: {{"action": string|null, "params": object, "confidence": 0..1, "reason"?: string}}
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        txt = resp.choices[0].message.content.strip()
        start, end = txt.find("{"), txt.rfind("}")
        data = json.loads(txt[start:end+1]) if start != - \
            1 else {"action": None, "params": {}, "confidence": 0}
        act = data.get("action")
        if act and act in RUNBOOKS:
            allowed = set(RUNBOOKS[act]["params"])
            data["params"] = {k: v for k, v in (
                data.get("params") or {}).items() if k in allowed}
        return data
    except Exception:
        return _rules(text)
