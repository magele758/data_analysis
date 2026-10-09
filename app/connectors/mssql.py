from typing import List, Optional
import pyarrow as pa
import connectorx as cx
from app.connectors.base import (
    BaseConnector, TableSchema, ColumnInfo, is_select, safe_select, sql_string_literal,
)
from app.engine.sql_guard import safe_columns, safe_ident, safe_predicate, safe_table_ref


def build_fetch_sql(
    query_or_table: str,
    filter_sql: Optional[str] = None,
    select_cols: Optional[List[str]] = None,
    limit: Optional[int] = None,
) -> str:
    """Build a SQL Server SELECT. TOP is applied after filters, including for caller-supplied SELECTs."""
    cols_clause = safe_columns(select_cols) if select_cols else "*"
    if is_select(query_or_table):
        base_sql = safe_select(query_or_table)
    else:
        base_sql = f"SELECT {cols_clause} FROM {safe_table_ref(query_or_table)}"
    if filter_sql:
        base_sql = f"SELECT * FROM ({base_sql}) AS _sub WHERE {safe_predicate(filter_sql)}"
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError(f"limit must be a non-negative integer, got {limit!r}")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        base_sql = f"SELECT TOP {limit} * FROM ({base_sql}) AS _lim"
    return base_sql


class MSSQLConnector(BaseConnector):
    """SQL Server (MSSQL) high-performance connector via ConnectorX."""

    def test_connection(self) -> bool:
        try:
            df = cx.read_sql(self.conn_str, "SELECT 1 AS ping", return_type="arrow")
            return len(df) > 0
        except Exception:
            return False

    def list_tables(self) -> List[str]:
        query = """
        SELECT TABLE_SCHEMA + '.' + TABLE_NAME AS full_name
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY 1;
        """
        table = cx.read_sql(self.conn_str, query, return_type="arrow")
        return [str(val) for val in table["full_name"].to_pylist()]

    def introspect_schema(self, table_name: str) -> TableSchema:
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError("table_name is required")
        parts = table_name.split(".")
        if len(parts) == 1:
            schema_part, table_part = "dbo", parts[0]
        elif len(parts) == 2:
            schema_part, table_part = parts
        else:
            raise ValueError(f"Expected schema.table, got {table_name!r}")
        query = f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = {sql_string_literal(schema_part)}
          AND TABLE_NAME = {sql_string_literal(table_part)}
        ORDER BY ORDINAL_POSITION;
        """
        arrow_res = cx.read_sql(self.conn_str, query, return_type="arrow")
        cols = []
        for row in arrow_res.to_pylist():
            cname = row["COLUMN_NAME"]
            dtype = str(row["DATA_TYPE"]).lower()
            nullable = (row["IS_NULLABLE"] == "YES")
            cols.append(ColumnInfo(name=cname, physical_type=dtype, is_nullable=nullable))

        return TableSchema(table_name=table_name, columns=cols)

    def fetch_to_arrow(
        self,
        query_or_table: str,
        filter_sql: Optional[str] = None,
        select_cols: Optional[List[str]] = None,
        partition_col: Optional[str] = None,
        num_partitions: int = 1,
        limit: Optional[int] = None,
        mode: str = "materialize"  # no DuckDB mssql scanner; always ConnectorX
    ) -> pa.Table:
        base_sql = build_fetch_sql(
            query_or_table,
            filter_sql=filter_sql,
            select_cols=select_cols,
            limit=limit,
        )

        if partition_col and num_partitions > 1:
            return cx.read_sql(
                self.conn_str,
                base_sql,
                partition_on=safe_ident(partition_col),
                partition_num=num_partitions,
                return_type="arrow"
            )
        return cx.read_sql(self.conn_str, base_sql, return_type="arrow")
