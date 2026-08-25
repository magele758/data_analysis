from typing import Dict, Any, List, Optional
import duckdb
import json

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
        cols = ", ".join(export_columns) if export_columns else "*"
        sql = f"SELECT {cols} FROM {source_table}"
        if filter_sql:
            sql += f" WHERE {filter_sql}"
        sql += f" LIMIT {limit}"

        df = con.execute(sql).df()
        
        if format_type.lower() == "csv":
            content = df.to_csv(index=False)
        else:
            content = df.to_dict(orient="records")

        return {
            "source_table": source_table,
            "total_audience_count": len(df),
            "format": format_type,
            "data": content
        }
