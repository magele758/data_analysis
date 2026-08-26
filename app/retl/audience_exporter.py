from typing import Dict, Any, List, Optional
import duckdb
import json

from app.engine.arrow_utils import ArrowUtils
from app.engine.sql_guard import safe_columns, safe_predicate, safe_table_ref

class AudienceExporter:
    @staticmethod
    def export_cohort(
        con: duckdb.DuckDBPyConnection,
        source_table: str,
        filter_sql: Optional[str] = None,
        export_columns: Optional[List[str]] = None,
        format_type: str = "json", # json, csv
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Extract specific audience segment / user cohort for activation into CRM or marketing tools.
        """
        cols = safe_columns(export_columns) if export_columns else "*"
        sql = f"SELECT {cols} FROM {safe_table_ref(source_table)}"
        if filter_sql:
            sql += f" WHERE {safe_predicate(filter_sql)}"
        sql += f" LIMIT {int(limit)}"

        df = con.execute(sql).df()
        
        if format_type.lower() == "csv":
            content = df.to_csv(index=False)
        else:
            content = ArrowUtils.df_to_records(df)

        return {
            "source_table": source_table,
            "total_audience_count": len(df),
            "format": format_type,
            "data": content
        }
