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

    return {
        "total_records": len(arrow_res),
        "schema": arrow_res.column_names,
        "records": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit)
    }

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

    return {
        "total_records": len(arrow_res),
        "schema": arrow_res.column_names,
        "records": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit)
    }
