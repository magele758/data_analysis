from typing import Dict, Any
from app.cluster.session_manager import SessionManager
from app.distributed_ops.dist_eda import DistributedEDA

def run_eda_profile(session_id: str, dataset_name: str) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()
    res = DistributedEDA.profile_table(con, dataset_name)
    try:
        from app.copilot.analysis_trail import get_trail_ledger
        ev = res.get("evidence") or {}
        get_trail_ledger(session_id).record_step(
            operator="eda_profile",
            method=ev.get("method", "single_pass_summarize"),
            dataset_name=dataset_name,
            parameters={"session_id": session_id, "dataset_name": dataset_name},
            summary=f"EDA profile on '{dataset_name}' ({res.get('total_rows', 0)} rows, quality={res.get('quality_score')})",
            sql=ev.get("sql") or [],
            warnings=ev.get("caveats") or [],
            duration_ms=ev.get("duration_ms"),
            rows_scanned=ev.get("rows_scanned"),
            rows_used=ev.get("rows_used"),
        )
    except Exception:
        pass
    return res
