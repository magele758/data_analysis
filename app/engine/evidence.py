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


def structured_evidence(*, operator, method, session_id, dataset_name, parameters,
                        population, metric_semantics, time_semantics, assumptions,
                        warnings, truncation, sql, duration_ms):
    """Versioned contract for composable tools and reports; legacy evidence stays compatible."""
    import hashlib
    from app.schemas.responses import ToolEvidence
    statements = list(sql)
    return ToolEvidence(
        operator=operator, method=method, session_id=session_id, dataset_name=dataset_name,
        parameters=parameters, population=population, metric_semantics=metric_semantics,
        time_semantics=time_semantics, assumptions=assumptions, warnings=warnings,
        truncation=truncation, sql=statements,
        query_sha256=hashlib.sha256('\n'.join(statements).encode()).hexdigest(),
        duration_ms=duration_ms, causal_claim=False,
    ).model_dump(mode='json')
