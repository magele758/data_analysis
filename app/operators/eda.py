from typing import Dict, Any
from app.cluster.session_manager import SessionManager
from app.distributed_ops.dist_eda import DistributedEDA

def run_eda_profile(session_id: str, dataset_name: str) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()
    return DistributedEDA.profile_table(con, dataset_name)
