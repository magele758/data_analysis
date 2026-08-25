from typing import List, Optional
import pyarrow as pa
import connectorx as cx
from app.connectors.base import BaseConnector, TableSchema, ColumnInfo

class MySQLConnector(BaseConnector):
    """MySQL high-performance connector using ConnectorX (Rust binary protocol)."""

    def test_connection(self) -> bool:
        try:
            df = cx.read_sql(self.conn_str, "SELECT 1 AS ping", return_type="arrow")
            return len(df) > 0
        except Exception:
            return False

    def list_tables(self) -> List[str]:
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        ORDER BY table_name;
        """
        table = cx.read_sql(self.conn_str, query, return_type="arrow")
        return [str(val) for val in table["table_name"].to_pylist()]

    def introspect_schema(self, table_name: str) -> TableSchema:
        query = f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = '{table_name}'
        ORDER BY ordinal_position;
        """
        arrow_res = cx.read_sql(self.conn_str, query, return_type="arrow")
        cols = []
        for row in arrow_res.to_pylist():
            cname = row["column_name"]
            dtype = str(row["data_type"]).lower()
            nullable = (row["is_nullable"] == "YES")
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
        cols_clause = ", ".join(select_cols) if select_cols else "*"
        if query_or_table.strip().upper().startswith("SELECT"):
            base_sql = query_or_table
        else:
            base_sql = f"SELECT {cols_clause} FROM {query_or_table}"

        if filter_sql:
            base_sql = f"SELECT * FROM ({base_sql}) AS _sub WHERE {filter_sql}"

        if limit:
            base_sql += f" LIMIT {limit}"

        if partition_col and num_partitions > 1:
            return cx.read_sql(
                self.conn_str,
                base_sql,
                partition_on=partition_col,
                partition_num=num_partitions,
                return_type="arrow"
            )
        return cx.read_sql(self.conn_str, base_sql, return_type="arrow")
