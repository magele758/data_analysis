from typing import Dict, Any, List, Optional
import duckdb

from app.engine.arrow_utils import ArrowUtils
from app.engine.sql_guard import safe_columns, safe_predicate, safe_table_ref

_FORMATS = ("json", "csv")


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

        total_audience_count is the full filter match. data holds at most `limit` rows.
        """
        if not isinstance(format_type, str) or format_type.lower() not in _FORMATS:
            raise ValueError(f"Unsupported audience format {format_type!r}: use 'json' or 'csv'")
        format_type = format_type.lower()
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")

        ref = safe_table_ref(source_table)
        cols = safe_columns(export_columns) if export_columns else "*"
        where = ""
        if filter_sql:
            where = f" WHERE {safe_predicate(filter_sql)}"

        total = con.execute(f"SELECT count(*) FROM {ref}{where}").fetchone()[0]
        df = con.execute(f"SELECT {cols} FROM {ref}{where} LIMIT {limit}").df()

        if format_type == "csv":
            content = df.to_csv(index=False)
        else:
            content = ArrowUtils.df_to_records(df)

        exported = len(df)
        return {
            "source_table": source_table,
            "total_audience_count": total,
            "exported_count": exported,
            "truncated": exported < total,
            "format": format_type,
            "data": content
        }
