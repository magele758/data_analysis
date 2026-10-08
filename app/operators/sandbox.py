import re
from typing import Dict, Any
import duckdb
import pyarrow as pa
from app.cluster.session_manager import SessionManager
from app.engine.arrow_utils import ArrowUtils

_EXTERNAL_FN = re.compile(
    r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|read_blob|read_text"
    r"|iceberg_scan|postgres_scan|mysql_scan|sqlite_scan|httpfs)\b",
    re.IGNORECASE,
)

# DuckDB StatementType names that only read. WITH/DESCRIBE/SHOW/PRAGMA-introspection all
# parse as SELECT. PIVOT/UNPIVOT parse as CREATE, so they stay out; use run_pivot_table.
_READ_ONLY_STATEMENTS = {"SELECT", "EXPLAIN"}


def _assert_read_only(clean_sql: str) -> str:
    """Require exactly one statement, and that it is a read.

    Returns the DuckDB statement type name. Raises PermissionError for anything else.
    """
    extract = getattr(duckdb, "extract_statements", None)
    if extract is None:
        raise PermissionError(
            "DuckDB statement extraction unavailable; cannot verify read-only SQL"
        )
    try:
        statements = extract(clean_sql)
    except Exception as exc:
        raise ValueError(f"Invalid SQL: {exc}") from exc

    if len(statements) != 1:
        raise PermissionError(
            f"Only a single statement is allowed in the read-only sandbox, got {len(statements)}"
        )

    stmt_type = getattr(statements[0].type, "name", str(statements[0].type))
    if stmt_type not in _READ_ONLY_STATEMENTS:
        raise PermissionError(
            f"Statement type '{stmt_type}' is forbidden in analytical read-only sandbox"
        )
    return stmt_type


def run_duckdb_sql(session_id: str, sql_query: str, limit: int = 100, governed: bool = False) -> Dict[str, Any]:
    """Execute ad-hoc DuckDB SQL within session memory sandbox safely."""
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")

    clean_sql = sql_query.strip().rstrip(";")
    if _EXTERNAL_FN.search(clean_sql):
        raise PermissionError(
            "External table functions are forbidden in the read-only sandbox"
        )
    stmt_type = _assert_read_only(clean_sql)

    # DESCRIBE/SHOW/SUMMARIZE report as SELECT but reject a trailing LIMIT.
    limitable = clean_sql.lstrip("( \t\n").upper().startswith(("SELECT", "WITH", "FROM", "TABLE"))
    if limit and stmt_type == "SELECT" and limitable and "LIMIT" not in clean_sql.upper():
        clean_sql += f" LIMIT {limit}"

    # The session connection also serves COPY exports, so external access is
    # turned off only for this query and restored under the session lock.
    con = sess.get_duckdb_conn()
    with sess._lock:
        try:
            con.execute("SET enable_external_access=false")
        except duckdb.Error:
            pass
        try:
            pending = con.execute(clean_sql).arrow()
            # Materialize before the next statement. A later SET invalidates the reader.
            if isinstance(pending, pa.RecordBatchReader):
                arrow_res = pending.read_all()
            else:
                arrow_res = pending
        finally:
            try:
                con.execute("SET enable_external_access=true")
            except duckdb.Error:
                pass
    return {
        "columns": arrow_res.column_names,
        "row_count": len(arrow_res),
        "data": ArrowUtils.table_to_compact_preview(arrow_res, limit=limit),
        "ungoverned_sql": not governed,
    }
