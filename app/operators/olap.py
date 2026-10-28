from typing import List, Dict, Any, Optional
from app.cluster.session_manager import SessionManager
from app.distributed_ops.dist_olap import DistributedOLAP
from app.engine.arrow_utils import ArrowUtils

def run_olap_query(
    session_id: str,
    dataset_name: str,
    dimensions: List[str],
    metrics: List[str],
    agg_funcs: Optional[List[str]] = None,
    filters: Optional[str] = None,
    rollup: bool = False,
    cube: bool = False,
    order_by: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    arrow_res = DistributedOLAP.aggregate(
        con=con,
        table_name=dataset_name,
        dimensions=dimensions,
        metrics=metrics,
        agg_funcs=agg_funcs,
        filters=filters,
        rollup=rollup,
        cube=cube,
        order_by=order_by,
        limit=limit
    )

    out = {
        "total_records": len(arrow_res),
        "schema": arrow_res.column_names,
        "records": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit)
    }
    try:
        from app.copilot.analysis_trail import get_trail_ledger
        get_trail_ledger(session_id).record_step(
            operator="memory_olap_aggregation",
            method="rollup" if rollup else ("cube" if cube else "group_by"),
            dataset_name=dataset_name,
            parameters={
                "session_id": session_id,
                "dataset_name": dataset_name,
                "dimensions": dimensions,
                "metrics": metrics,
                "agg_funcs": agg_funcs,
                "filters": filters,
                "rollup": rollup,
                "cube": cube,
                "order_by": order_by,
                "limit": limit,
            },
            summary=f"OLAP aggregation on '{dataset_name}' ({len(arrow_res)} rows)",
            rows_used=len(arrow_res),
        )
    except Exception:
        pass
    return out

def run_pivot_table(
    session_id: str,
    dataset_name: str,
    rows: List[str],
    columns: str,
    values: str,
    agg_func: str = "SUM",
    filters: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    arrow_res = DistributedOLAP.pivot_table(
        con=con,
        table_name=dataset_name,
        rows=rows,
        columns=columns,
        values=values,
        agg_func=agg_func,
        filters=filters
    )

    out = {
        "total_records": len(arrow_res),
        "schema": arrow_res.column_names,
        "records": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit)
    }
    try:
        from app.copilot.analysis_trail import get_trail_ledger
        get_trail_ledger(session_id).record_step(
            operator="pivot_table",
            method=agg_func,
            dataset_name=dataset_name,
            parameters={
                "session_id": session_id,
                "dataset_name": dataset_name,
                "rows": rows,
                "columns": columns,
                "values": values,
                "agg_func": agg_func,
                "filters": filters,
                "limit": limit,
            },
            summary=f"Pivot table on '{dataset_name}' ({len(arrow_res)} rows)",
            rows_used=len(arrow_res),
        )
    except Exception:
        pass
    return out
