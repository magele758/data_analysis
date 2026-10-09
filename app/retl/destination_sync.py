import os
import sqlite3
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import duckdb
import psycopg
import pyarrow as pa
import pymysql

from app.engine.sql_guard import safe_ident, safe_table_ref

# Small, boring DuckDB -> destination type mapping. Anything unmatched falls back to TEXT.
_PG_TYPES = {
    "BOOLEAN": "BOOLEAN", "TINYINT": "SMALLINT", "SMALLINT": "SMALLINT",
    "INTEGER": "INTEGER", "BIGINT": "BIGINT", "HUGEINT": "NUMERIC",
    "UTINYINT": "SMALLINT", "USMALLINT": "INTEGER", "UINTEGER": "BIGINT",
    "UBIGINT": "NUMERIC", "FLOAT": "REAL", "DOUBLE": "DOUBLE PRECISION",
    "DATE": "DATE", "TIME": "TIME", "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ", "UUID": "UUID",
    "VARCHAR": "TEXT", "BLOB": "BYTEA",
}
_MYSQL_TYPES = {
    "BOOLEAN": "TINYINT(1)", "TINYINT": "TINYINT", "SMALLINT": "SMALLINT",
    "INTEGER": "INT", "BIGINT": "BIGINT", "HUGEINT": "DECIMAL(38,0)",
    "UTINYINT": "SMALLINT", "USMALLINT": "INT", "UINTEGER": "BIGINT",
    "UBIGINT": "DECIMAL(20,0)", "FLOAT": "FLOAT", "DOUBLE": "DOUBLE",
    "DATE": "DATE", "TIME": "TIME", "TIMESTAMP": "DATETIME",
    "TIMESTAMP WITH TIME ZONE": "DATETIME", "UUID": "CHAR(36)",
    "VARCHAR": "TEXT", "BLOB": "BLOB",
}


def _source_schema(con: duckdb.DuckDBPyConnection, quoted_source: str) -> List[Tuple[str, str]]:
    """Return [(column_name, duckdb_type)] for the source table."""
    rows = con.execute(f"DESCRIBE SELECT * FROM {quoted_source}").fetchall()
    return [(r[0], str(r[1]).upper()) for r in rows]


def _map_type(duck_type: str, type_map: Dict[str, str]) -> str:
    base = duck_type.split("(")[0].strip()
    if base.startswith("DECIMAL"):
        return duck_type
    return type_map.get(duck_type) or type_map.get(base) or "TEXT"


def _sqlite_type(duck_type: str) -> str:
    base = duck_type.split("(")[0].strip()
    # REAL/NUMERIC affinity stores IEEE floats. DECIMAL stays TEXT so the
    # exact digit string is what gets bound.
    if base == "DECIMAL":
        return "TEXT"
    if base in ("FLOAT", "DOUBLE", "REAL"):
        return "REAL"
    if base == "BLOB":
        return "BLOB"
    if "INT" in base or base == "BOOLEAN":
        return "INTEGER"
    return "TEXT"


def _validate_chunk_size(chunk_size: int) -> int:
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError(f"chunk_size must be a positive integer, got {chunk_size!r}")
    return chunk_size


def _iter_batches(con: duckdb.DuckDBPyConnection, quoted_source: str, chunk_size: int):
    """Stream the source as Arrow record batches. One batch is in memory at a time."""
    reader = con.execute(f"SELECT * FROM {quoted_source}").to_arrow_reader(chunk_size)
    try:
        for batch in reader:
            if batch.num_rows:
                yield batch
    finally:
        close = getattr(reader, "close", None)
        if close is not None:
            close()


def _rows_from_batch(batch: pa.RecordBatch, columns: Sequence[str]) -> List[Tuple[Any, ...]]:
    return [tuple(record.get(col) for col in columns) for record in batch.to_pylist()]


def _sqlite_param(value: Any) -> Any:
    """Values sqlite3 will bind without the deprecated default adapters.

    Decimal is the exact digit string. sqlite3 cannot bind Decimal, and float()
    rounds anything past about 15 significant digits.
    """
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _file_export_path(dest_conn_str: str, scheme: str) -> Optional[str]:
    if scheme == "file":
        path = dest_conn_str[len("file://"):] if dest_conn_str.lower().startswith("file://") else dest_conn_str
    elif scheme == "":
        path = dest_conn_str
    else:
        return None
    if not path.lower().endswith((".parquet", ".csv")):
        return None
    return path


def _sqlite_db_path(dest_conn_str: str, parsed) -> str:
    """Resolve a sqlite URL or bare path.

    sqlite:///data/app.db stays relative (data/app.db). sqlite:////tmp/app.db is absolute.
    A bare path is used as given, so /tmp/app.db is not stripped into a relative path.
    """
    scheme = parsed.scheme.lower()
    if scheme in ("sqlite", "sqlite3"):
        path = parsed.path or ""
        if path.startswith("//"):
            return path[1:]
        if path.startswith("/"):
            return path[1:]
        cleaned = dest_conn_str.replace("sqlite:///", "").replace("sqlite://", "")
        return cleaned or "data/destination_sync.db"
    if not dest_conn_str:
        return "data/destination_sync.db"
    return dest_conn_str


class DestinationSync:
    @staticmethod
    def sync_table_to_destination(
        con: duckdb.DuckDBPyConnection,
        source_table: str,
        dest_conn_str: str,
        dest_table_name: str,
        mode: str = "replace", # replace, append
        chunk_size: int = 50000
    ) -> Dict[str, Any]:
        """
        Stream a session table to PostgreSQL, MySQL, SQLite, Parquet, or CSV.

        Database destinations read Arrow record batches of `chunk_size` rows and
        insert each batch. File destinations use DuckDB COPY and only support
        mode='replace'.
        """
        start_t = time.time()

        if mode not in ("replace", "append"):
            raise ValueError(f"Unsupported sync mode '{mode}': use 'replace' or 'append'")
        chunk_size = _validate_chunk_size(chunk_size)

        quoted_source = safe_table_ref(source_table)
        safe_ident(dest_table_name)

        parsed = urlparse(dest_conn_str)
        scheme = parsed.scheme.lower()
        file_path = _file_export_path(dest_conn_str, scheme)

        if scheme in ("postgres", "postgresql", "mysql"):
            synced_rows = DestinationSync._sync_to_rdbms(
                con, quoted_source, dest_table_name, dest_conn_str, scheme,
                mode, chunk_size,
            )
        elif file_path is not None:
            synced_rows = DestinationSync._sync_to_file(con, quoted_source, file_path, mode)
        elif scheme in ("sqlite", "sqlite3", ""):
            db_path = _sqlite_db_path(dest_conn_str, parsed)
            synced_rows = DestinationSync._sync_to_sqlite(
                con, quoted_source, db_path, dest_table_name, mode, chunk_size,
            )
        else:
            raise NotImplementedError(
                f"Unsupported reverse-ETL destination scheme '{scheme or dest_conn_str}'"
            )

        duration_ms = round((time.time() - start_t) * 1000, 2)

        return {
            "source_table": source_table,
            "dest_conn_str": dest_conn_str,
            "dest_table_name": dest_table_name,
            "synced_rows": synced_rows,
            "mode": mode,
            "duration_ms": duration_ms,
            "status": "SUCCESS"
        }

    @staticmethod
    def _sync_to_file(
        con: duckdb.DuckDBPyConnection,
        quoted_source: str,
        file_path: str,
        mode: str,
    ) -> int:
        if mode != "replace":
            raise ValueError(
                "File destinations only support mode='replace'; "
                f"mode={mode!r} would overwrite or corrupt the existing file"
            )
        if not file_path or any(ch in file_path for ch in ("\x00", "\n", "\r")):
            raise ValueError(f"Invalid export path {file_path!r}")
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # Bind the path. Interpolating it would let a quote close the COPY string.
        if file_path.lower().endswith(".parquet"):
            con.execute(
                f"COPY {quoted_source} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                [file_path],
            )
        else:
            con.execute(
                f"COPY {quoted_source} TO ? (FORMAT CSV, HEADER)",
                [file_path],
            )
        return con.execute(f"SELECT count(*) FROM {quoted_source}").fetchone()[0]

    @staticmethod
    def _sync_to_sqlite(
        con: duckdb.DuckDBPyConnection,
        quoted_source: str,
        db_path: str,
        dest_table_name: str,
        mode: str,
        chunk_size: int,
    ) -> int:
        schema = _source_schema(con, quoted_source)
        for name, _ in schema:
            safe_ident(name)
        dest_ref = safe_ident(dest_table_name)
        columns = [name for name, _ in schema]
        ddl_cols = ", ".join(
            f"{safe_ident(name)} {_sqlite_type(duck_type)}" for name, duck_type in schema
        )
        placeholders = ", ".join(["?"] * len(schema))
        col_list = ", ".join(safe_ident(name) for name in columns)
        insert_sql = f"INSERT INTO {dest_ref} ({col_list}) VALUES ({placeholders})"

        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        s_con = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
        written = 0
        try:
            s_con.execute("PRAGMA journal_mode=WAL")
            s_con.execute("BEGIN")
            try:
                if mode == "replace":
                    s_con.execute(f"DROP TABLE IF EXISTS {dest_ref}")
                s_con.execute(f"CREATE TABLE IF NOT EXISTS {dest_ref} ({ddl_cols})")
                for batch in _iter_batches(con, quoted_source, chunk_size):
                    rows = [
                        tuple(_sqlite_param(value) for value in row)
                        for row in _rows_from_batch(batch, columns)
                    ]
                    s_con.executemany(insert_sql, rows)
                    written += len(rows)
                s_con.commit()
            except Exception:
                s_con.rollback()
                raise
        finally:
            s_con.close()
        return written

    @staticmethod
    def _sync_to_rdbms(
        con: duckdb.DuckDBPyConnection,
        quoted_source: str,
        dest_table_name: str,
        dest_conn_str: str,
        scheme: str,
        mode: str,
        chunk_size: int,
    ) -> int:
        """Chunked, transactional write to PostgreSQL or MySQL. Returns rows written."""
        is_pg = scheme in ("postgres", "postgresql")

        if is_pg:
            dest_con = psycopg.connect(dest_conn_str, autocommit=False)
            quote = '"'
            type_map = _PG_TYPES
        else:
            parsed = urlparse(dest_conn_str)
            dest_con = pymysql.connect(
                host=parsed.hostname or "localhost",
                port=parsed.port or 3306,
                user=parsed.username or "",
                password=parsed.password or "",
                database=(parsed.path or "").lstrip("/") or None,
                autocommit=False,
            )
            quote = "`"
            type_map = _MYSQL_TYPES

        schema = _source_schema(con, quoted_source)
        for name, _ in schema:
            safe_ident(name)

        dest_ref = f"{quote}{dest_table_name}{quote}"
        columns = [name for name, _ in schema]
        col_list = ", ".join(f"{quote}{name}{quote}" for name in columns)
        placeholders = ", ".join(["%s"] * len(schema))
        insert_sql = f"INSERT INTO {dest_ref} ({col_list}) VALUES ({placeholders})"
        ddl_cols = ", ".join(
            f"{quote}{name}{quote} {_map_type(duck_type, type_map)}" for name, duck_type in schema
        )

        written = 0
        try:
            with dest_con.cursor() as cur:
                if mode == "replace":
                    cur.execute(f"DROP TABLE IF EXISTS {dest_ref}")
                    cur.execute(f"CREATE TABLE {dest_ref} ({ddl_cols})")
                else:
                    cur.execute(f"CREATE TABLE IF NOT EXISTS {dest_ref} ({ddl_cols})")

                for batch in _iter_batches(con, quoted_source, chunk_size):
                    rows = _rows_from_batch(batch, columns)
                    cur.executemany(insert_sql, rows)
                    written += len(rows)
            dest_con.commit()
        except Exception:
            dest_con.rollback()
            raise
        finally:
            dest_con.close()

        return written
