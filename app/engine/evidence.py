"""Standard evidence envelope attached to operator results.

Callers narrate these fields. They do not recompute them.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def evidence(
    *,
    operator: str,
    sql: Optional[List[str]] = None,
    rows_scanned: Optional[int] = None,
    rows_used: Optional[int] = None,
    nulls_dropped: Optional[int] = None,
    duration_ms: Optional[float] = None,
    caveats: Optional[List[str]] = None,
    method: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "operator": operator,
        "method": method,
        "sql": list(sql or []),
        "rows_scanned": rows_scanned,
        "rows_used": rows_used,
        "nulls_dropped": nulls_dropped,
        "duration_ms": duration_ms,
        "caveats": list(caveats or []),
    }


class Stopwatch:
    def __init__(self) -> None:
        self._t = time.perf_counter()

    def ms(self) -> float:
        return round((time.perf_counter() - self._t) * 1000, 2)
