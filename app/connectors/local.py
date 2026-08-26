import os
from typing import List, Optional
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.csv as pcsv
import duckdb
from app.connectors.base import BaseConnector, TableSchema, ColumnInfo
from app.connectors.excel_reader import FastExcelReader
from app.engine.sql_guard import safe_columns, safe_ident, safe_predicate, safe_table_ref

class LocalFileConnector(BaseConnector):
    """Local Parquet / CSV / Excel (.xlsx, .xls) / SQLite / Arrow file connector."""

    def test_connection(self) -> bool:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        return os.path.exists(path)

    def list_tables(self) -> List[str]:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        if path.endswith((".xlsx", ".xls")):
            try:
                import zipfile
                with zipfile.ZipFile(path) as z:
                    return FastExcelReader.list_sheet_names(z)
            except Exception:
                return ["Sheet1"]
        elif path.endswith(".sqlite") or path.endswith(".db"):
            con = duckdb.connect(path, read_only=True)
            res = con.execute("SHOW TABLES").fetchall()
            con.close()
            return [r[0] for r in res]
        return [os.path.basename(path)]

    def introspect_schema(self, table_name: str) -> TableSchema:
        path = self.conn_str.replace("file://", "").replace("sqlite://", "")
        cols = []
        if path.endswith((".xlsx", ".xls")):
            arrow_tbl = FastExcelReader.read_xlsx_to_arrow(path, sheet_name=table_name, limit_rows=10)
            for field in arrow_tbl.schema:
                cols.append(ColumnInfo(name=field.name, physical_type=str(field.type), is_nullable=field.nullable))
        elif path.endswith(".parquet"):
            schema = pq.read_schema(path)
            for field in schema:
                cols.append(ColumnInfo(name=field.name, physical_type=str(field.type), is_nullable=field.nullable))
        elif path.endswith(".csv"):
            table = pcsv.read_csv(path)
            for field in table.schema:
                cols.append(ColumnInfo(name=field.name, physical_type=str(field.type), is_nullable=field.nullable))
        elif path.endswith(".sqlite") or path.endswith(".db"):
            con = duckdb.connect(path, read_only=True)
            desc = con.execute(f"DESCRIBE {safe_table_ref(table_name)}").fetchall()
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
        
        # 1. Excel direct high-performance ingestion
        if path.endswith((".xlsx", ".xls")):
            sheet = query_or_table if query_or_table and not query_or_table.lower().startswith("select") else None
            arrow_table = FastExcelReader.read_xlsx_to_arrow(
                path,
                sheet_name=sheet,
                limit_rows=limit
            )
            if select_cols or filter_sql:
                con = duckdb.connect(":memory:")
                con.register("excel_tmp", arrow_table)
                cols_clause = safe_columns(select_cols) if select_cols else "*"
                sql = f"SELECT {cols_clause} FROM excel_tmp"
                if filter_sql:
                    sql += f" WHERE {safe_predicate(filter_sql)}"
                params = []
                if limit:
                    sql += " LIMIT ?"
                    params.append(int(limit))
                arrow_table = con.execute(sql, params).arrow()
                if isinstance(arrow_table, pa.RecordBatchReader):
                    arrow_table = arrow_table.read_all()
                con.close()
            return arrow_table

        # 2. CSV / Parquet / SQLite via DuckDB
        con = duckdb.connect(":memory:")
        if path.endswith(".parquet"):
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM read_parquet('{path}')")
        elif path.endswith(".csv"):
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM read_csv_auto('{path}', sample_size=100000, ignore_errors=true)")
        elif path.endswith(".sqlite") or path.endswith(".db"):
            con.execute(f"ATTACH '{path}' AS sqlite_db (TYPE SQLITE)")
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM sqlite_db.{safe_ident(query_or_table)}")
        else:
            con.execute(f"CREATE VIEW tbl AS SELECT * FROM '{path}'")

        cols_clause = safe_columns(select_cols) if select_cols else "*"
        sql = f"SELECT {cols_clause} FROM tbl"
        if filter_sql:
            sql += f" WHERE {safe_predicate(filter_sql)}"
        params = []
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))

        arrow_table = con.execute(sql, params).arrow()
        if isinstance(arrow_table, pa.RecordBatchReader):
            arrow_table = arrow_table.read_all()
        con.close()
        return arrow_table
