import os
from typing import List, Optional
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.csv as pcsv
import duckdb
from app.connectors.base import BaseConnector, TableSchema, ColumnInfo

class LocalFileConnector(BaseConnector):
    """Local Parquet / CSV / SQLite / Arrow file connector."""

    def test_connection(self) -> bool:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        return os.path.exists(path)

    def list_tables(self) -> List[str]:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        if path.endswith(".sqlite") or path.endswith(".db"):
            con = duckdb.connect(path, read_only=True)
            res = con.execute("SHOW TABLES").fetchall()
            con.close()
            return [r[0] for r in res]
        return [os.path.basename(path)]

    def introspect_schema(self, table_name: str) -> TableSchema:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        cols = []
        if path.endswith(".parquet"):
            schema = pq.read_schema(path)
            for field in schema:
                cols.append(ColumnInfo(name=field.name, physical_type=str(field.type), is_nullable=field.nullable))
        elif path.endswith(".csv"):
            # Sample read
            table = pcsv.read_csv(path)
            for field in table.schema:
                cols.append(ColumnInfo(name=field.name, physical_type=str(field.type), is_nullable=field.nullable))
        elif path.endswith(".sqlite") or path.endswith(".db"):
            con = duckdb.connect(path, read_only=True)
            desc = con.execute(f"DESCRIBE {table_name}").fetchall()
            con.close()
            for r in desc:
                cols.append(ColumnInfo(name=r[0], physical_type=str(r[1]).lower(), is_nullable=(r[2] == 'YES')))
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
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        con = duckdb.connect(":memory:")
        if path.endswith(".parquet"):
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM read_parquet('{path}')")
        elif path.endswith(".csv"):
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM read_csv_auto('{path}')")
        elif path.endswith(".sqlite") or path.endswith(".db"):
            con.execute(f"ATTACH '{path}' AS sqlite_db (TYPE SQLITE)")
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM sqlite_db.{query_or_table}")
        else:
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM '{path}'")

        cols_clause = ", ".join(select_cols) if select_cols else "*"
        sql = f"SELECT {cols_clause} FROM tbl"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        if limit:
            sql += f" LIMIT {limit}"

        arrow_table = con.execute(sql).arrow()
        if isinstance(arrow_table, pa.RecordBatchReader):
            arrow_table = arrow_table.read_all()
        con.close()
        return arrow_table
