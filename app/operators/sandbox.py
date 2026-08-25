from typing import Dict, Any
from app.cluster.session_manager import SessionManager
from app.engine.arrow_utils import ArrowUtils

def run_duckdb_sql(session_id: str, sql_query: str, limit: int = 100) -> Dict[str, Any]:
    """Execute ad-hoc DuckDB SQL within session memory sandbox safely."""
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")

    clean_sql = sql_query.strip().rstrip(";")
    # Disallow destructive DDL/DML statements
    forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "ATTACH", "COPY"]
    first_word = clean_sql.split()[0].upper() if clean_sql else ""
    if first_word in forbidden:
        raise PermissionError(f"Operation '{first_word}' is forbidden in analytical read-only sandbox")

    arrow_res = sess.execute_sql(clean_sql, limit=limit)
    if isinstance(arrow_res, pa.RecordBatchReader):
        arrow_res = arrow_res.read_all()
    return {
        "columns": arrow_res.column_names,
        "row_count": len(arrow_res),
        "data": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit)
    }
