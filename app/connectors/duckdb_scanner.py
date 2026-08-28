"""DuckDB scanner-based extraction (ATTACH + predicate pushdown).

An alternative to ConnectorX materialization for RDBMS sources: instead of a Rust
client pulling the whole result, DuckDB ATTACHes the external database via its
native scanner extension (postgres/mysql/sqlite) and runs the query directly,
pushing projections/filters down to the source. Data is still returned as Arrow
for the in-memory session, but the extraction path is DuckDB-native — one SQL
dialect, fewer moving parts, and no dependency on ConnectorX for this path.

ConnectorX materialization stays the default; this is opt-in via mode="scanner".
"""

from typing import Optional
from urllib.parse import urlparse

import duckdb
import pyarrow as pa

# DuckDB scanner extension name per source type.
_EXTENSION = {
    "postgres": "postgres", "postgresql": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite", "sqlite3": "sqlite",
}
_ATTACH_TYPE = {
    "postgres": "POSTGRES", "postgresql": "POSTGRES",
    "mysql": "MYSQL",
    "sqlite": "SQLITE", "sqlite3": "SQLITE",
}


def _mysql_dsn(conn_str: str) -> str:
    """DuckDB's MySQL scanner wants a key=value DSN, not a mysql:// URI."""
    p = urlparse(conn_str)
    parts = []
    if p.hostname:
        parts.append(f"host={p.hostname}")
    if p.port:
        parts.append(f"port={p.port}")
    if p.username:
        parts.append(f"user={p.username}")
    if p.password:
        parts.append(f"password={p.password}")
    db = (p.path or "").lstrip("/")
    if db:
        parts.append(f"database={db}")
    return " ".join(parts)


def _sqlite_path(conn_str: str) -> str:
    return conn_str.replace("sqlite:///", "").replace("sqlite://", "").replace("file://", "")


def attach_target(db_type: str, conn_str: str) -> str:
    """Return the connection payload DuckDB's ATTACH expects for this source.

    - Postgres: a libpq conninfo / postgresql:// URI is accepted as-is.
    - MySQL: converted to a key=value DSN.
    - SQLite: the file path.
    """
    t = db_type.lower()
    if t in ("postgres", "postgresql"):
        return conn_str
    if t == "mysql":
        return _mysql_dsn(conn_str)
    if t in ("sqlite", "sqlite3"):
        return _sqlite_path(conn_str)
    raise ValueError(f"Unsupported scanner source type: {db_type}")


def attach_clause(db_type: str, conn_str: str, alias: str = "src", read_only: bool = True) -> str:
    """Build the DuckDB ATTACH statement (pure/testable)."""
    t = db_type.lower()
    if t not in _ATTACH_TYPE:
        raise ValueError(f"Unsupported scanner source type: {db_type}")
    target = attach_target(t, conn_str).replace("'", "''")
    opts = [f"TYPE {_ATTACH_TYPE[t]}"]
    # SQLite ATTACH does not accept READ_ONLY as an option here; keep it for RDBMS.
    if read_only and t != "sqlite" and t != "sqlite3":
        opts.append("READ_ONLY")
    return f"ATTACH '{target}' AS {alias} ({', '.join(opts)})"


def fetch_via_scanner(db_type: str, conn_str: str, pushdown_sql: str, alias: str = "src") -> pa.Table:
    """ATTACH the external DB and run pushdown_sql against it, returning Arrow.

    pushdown_sql references bare table names; `USE <alias>` makes them resolve
    inside the attached database, so both a table read and a custom SELECT work.
    """
    t = db_type.lower()
    ext = _EXTENSION.get(t)
    if ext is None:
        raise ValueError(f"Unsupported scanner source type: {db_type}")

    con = duckdb.connect(":memory:")
    try:
        # Let DuckDB pull the scanner extension if it is not already present.
        try:
            con.execute("SET autoinstall_known_extensions=true")
            con.execute("SET autoload_known_extensions=true")
        except duckdb.Error:
            pass
        # sqlite is bundled; postgres/mysql may need an explicit install/load.
        if ext != "sqlite":
            try:
                con.execute(f"INSTALL {ext}")
                con.execute(f"LOAD {ext}")
            except duckdb.Error:
                pass
        con.execute(attach_clause(t, conn_str, alias))
        con.execute(f"USE {alias}")
        result = con.execute(pushdown_sql).arrow()
        if isinstance(result, pa.RecordBatchReader):
            result = result.read_all()
        return result
    finally:
        con.close()
