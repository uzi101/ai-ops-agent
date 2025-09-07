# Purpose: a single registry (dictionary) where every runbook function is registered by name.
# Both the CLI and Modal will import from here so there is no duplication.

from typing import Callable, Dict, Any

# global map: action name -> function
RUNBOOKS: Dict[str, Callable[..., Any]] = {}


def register(name: str | None = None):
    """
    Decorator used above each runbook function.
    When you define a runbook, decorate it with @register("action_name") to add it to RUNBOOKS.
    If name is omitted, it uses the function's name.
    """
    def _wrap(fn: Callable[..., Any]):
        key = name or fn.__name__   # use provided name or the function name
        RUNBOOKS[key] = fn          # store it in the global registry
        return fn                   # return the original function unchanged
    return _wrap


def list_actions() -> list[str]:
    """Helper to list actions in a stable (sorted) order."""
    return sorted(RUNBOOKS.keys())
