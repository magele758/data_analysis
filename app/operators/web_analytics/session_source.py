"""Shared access to a session-resident trace/event table.

Trace analytics used to read a dedicated on-disk event_store. After the refactor
they run on whatever trace dataset was imported into the in-memory analytical
session, so the DB-connector path and the trace path share one analysis engine.
"""

from typing import Any, Dict, List, Optional

from app.cluster.session_manager import SessionManager
from app.engine.sql_guard import safe_table_ref

# created_at arrives as an ISO string from import; TRY_CAST tolerates the trailing
# 'Z' and the 'T' separator and yields NULL (not an error) on anything unparseable.
CREATED_AT_TS = "TRY_CAST(created_at AS TIMESTAMP)"


def resolve_table(session_id: str, table_name: str):
    """Return (duckdb_conn, safe_table_ref) or raise if the session is missing."""
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    return sess.get_duckdb_conn(), safe_table_ref(table_name)


def query(session_id: str, table_name: str, sql: str, params: Optional[list] = None) -> List[Dict[str, Any]]:
    """Run parameterized SQL against a session table, returning list-of-dicts."""
    con, _ = resolve_table(session_id, table_name)
    cur = con.execute(sql, params) if params else con.execute(sql)
    df = cur.df()
    return df.to_dict(orient="records")
