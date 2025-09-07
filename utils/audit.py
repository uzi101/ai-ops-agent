# Append-only audit log: one JSON record per event, written to audit/audit.jsonl

import json
import os
import time
import uuid
from datetime import datetime

# Directory can be overridden for tests via env var
AUDIT_DIR = os.environ.get("LINOPS_AUDIT_DIR", "audit")
os.makedirs(AUDIT_DIR, exist_ok=True)

AUDIT_PATH = os.path.join(AUDIT_DIR, "audit.jsonl")


def audit_log(event: str, **payload):
    """
    Write a single audit record (plan/do/refusal/shell_exec/etc.).
    Returns the record dict so callers can reuse it in responses/tests.
    """
    record = {
        "id": str(uuid.uuid4()),                 # unique id per event
        "event": event,                          # e.g., "plan", "do", "refusal", "shell_exec"
        "ts": time.time(),                       # unix timestamp (float)
        "iso": datetime.utcnow().isoformat() + "Z",  # ISO8601 timestamp (UTC)
        **payload,                               # any additional fields provided by caller
    }
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
