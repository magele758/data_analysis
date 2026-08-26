from typing import List, Optional
import pyarrow as pa
import connectorx as cx
from app.connectors.base import BaseConnector, TableSchema, ColumnInfo, is_select, safe_select
from app.engine.sql_guard import safe_columns, safe_ident, safe_predicate, safe_table_ref

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
        schema_part = "dbo"
        table_part = table_name
        if "." in table_name:
            schema_part, table_part = table_name.split(".", 1)

        query = f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema_part}' AND TABLE_NAME = '{table_part}'
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
        limit: Optional[int] = None
    ) -> pa.Table:
        cols_clause = safe_columns(select_cols) if select_cols else "*"
        if is_select(query_or_table):
            base_sql = safe_select(query_or_table)
        else:
            top_clause = f"TOP {int(limit)} " if limit else ""
            base_sql = f"SELECT {top_clause}{cols_clause} FROM {safe_table_ref(query_or_table)}"

        if filter_sql:
            base_sql = f"SELECT * FROM ({base_sql}) AS _sub WHERE {safe_predicate(filter_sql)}"

        if partition_col and num_partitions > 1:
            return cx.read_sql(
                self.conn_str,
                base_sql,
                partition_on=safe_ident(partition_col),
                partition_num=num_partitions,
                return_type="arrow"
            )
        return cx.read_sql(self.conn_str, base_sql, return_type="arrow")
