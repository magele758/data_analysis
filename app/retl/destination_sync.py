from typing import Dict, Any, List, Tuple
import duckdb
import sqlite3
from urllib.parse import urlparse
import time

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
        Production Streaming Reverse ETL:
        Syncs data in constant-memory batches using Arrow RecordBatches / PyArrow chunks.
        """
        start_t = time.time()

        if mode not in ("replace", "append"):
            raise ValueError(f"Unsupported sync mode '{mode}': use 'replace' or 'append'")

        quoted_source = safe_table_ref(source_table)
        quoted_dest = safe_ident(dest_table_name)

        total_rows = con.execute(f"SELECT count(*) FROM {quoted_source}").fetchone()[0]
        synced_rows = 0

        parsed = urlparse(dest_conn_str)
        scheme = parsed.scheme.lower()

        if scheme in ("postgres", "postgresql", "mysql"):
            synced_rows = DestinationSync._sync_to_rdbms(
                con, quoted_source, dest_table_name, dest_conn_str, scheme,
                mode, chunk_size, total_rows
            )

        elif scheme in ("file", "") and (dest_conn_str.endswith(".parquet") or dest_conn_str.endswith(".csv")):
            file_path = dest_conn_str.replace("file://", "")
            if file_path.endswith(".parquet"):
                # DuckDB zero-copy direct Parquet export
                con.execute(f"COPY {quoted_source} TO '{file_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            else:
                con.execute(f"COPY {quoted_source} TO '{file_path}' (FORMAT CSV, HEADER)")
            synced_rows = total_rows

        elif scheme in ("sqlite", "sqlite3", ""):
            db_path = parsed.path.lstrip("/") or dest_conn_str.replace("sqlite:///", "").replace("sqlite://", "")
            if not db_path:
                db_path = "data/destination_sync.db"

            with sqlite3.connect(db_path, timeout=30.0) as s_con:
                s_con.execute("PRAGMA journal_mode=WAL")

                # Fetch cursor in chunks
                offset = 0
                first_chunk = True
                while offset < total_rows:
                    chunk_df = con.execute(
                        f"SELECT * FROM {quoted_source} LIMIT {chunk_size} OFFSET {offset}"
                    ).df()

                    if_exists_mode = "replace" if (first_chunk and mode == "replace") else "append"
                    chunk_df.to_sql(dest_table_name, s_con, if_exists=if_exists_mode, index=False)
                    first_chunk = False
                    offset += chunk_size
                    synced_rows += len(chunk_df)

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
    def _sync_to_rdbms(
        con: duckdb.DuckDBPyConnection,
        quoted_source: str,
        dest_table_name: str,
        dest_conn_str: str,
        scheme: str,
        mode: str,
        chunk_size: int,
        total_rows: int,
    ) -> int:
        """Chunked, transactional write to PostgreSQL or MySQL. Returns rows written."""
        is_pg = scheme in ("postgres", "postgresql")

        if is_pg:
            import psycopg  # noqa: F401 -- clear ImportError if the driver is missing
            dest_con = psycopg.connect(dest_conn_str, autocommit=False)
            quote = '"'
            type_map = _PG_TYPES
        else:
            import pymysql  # noqa: F401
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
        col_list = ", ".join(f"{quote}{n}{quote}" for n, _ in schema)
        placeholders = ", ".join(["%s"] * len(schema))
        insert_sql = f"INSERT INTO {dest_ref} ({col_list}) VALUES ({placeholders})"
        ddl_cols = ", ".join(
            f"{quote}{n}{quote} {_map_type(t, type_map)}" for n, t in schema
        )

        written = 0
        try:
            with dest_con.cursor() as cur:
                if mode == "replace":
                    cur.execute(f"DROP TABLE IF EXISTS {dest_ref}")
                    cur.execute(f"CREATE TABLE {dest_ref} ({ddl_cols})")
                else:
                    cur.execute(f"CREATE TABLE IF NOT EXISTS {dest_ref} ({ddl_cols})")

                offset = 0
                while offset < total_rows:
                    rows = con.execute(
                        f"SELECT * FROM {quoted_source} LIMIT {chunk_size} OFFSET {offset}"
                    ).fetchall()
                    if not rows:
                        break
                    cur.executemany(insert_sql, rows)
                    written += len(rows)
                    offset += chunk_size
            dest_con.commit()
        except Exception:
            dest_con.rollback()
            raise
        finally:
            dest_con.close()

        return written

