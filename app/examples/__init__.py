"""Built-in, runnable analysis examples exposed to the web dashboard and CLI.

Each example generates a seeded in-memory dataset, runs the full service pipeline,
and returns a structured result (including a Markdown report). Keeping them here
makes the app the single source of truth so the dashboard, REST API, and the
examples/ CLI scripts all share one implementation.
"""

from typing import Any, Dict, List, Optional

from app.examples import erp, dota2

_REGISTRY = {erp.EXAMPLE_ID: erp, dota2.EXAMPLE_ID: dota2}


def list_examples() -> List[Dict[str, str]]:
    return [
        {"id": m.EXAMPLE_ID, "name": m.NAME, "domain": m.DOMAIN, "description": m.DESCRIPTION}
        for m in _REGISTRY.values()
    ]


def run_example(example_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    mod = _REGISTRY.get(example_id)
    if mod is None:
        raise ValueError(f"Unknown example '{example_id}'. Available: {', '.join(_REGISTRY)}")
    return mod.run_in_memory(session_id=session_id)


__all__ = ["list_examples", "run_example", "erp", "dota2"]
