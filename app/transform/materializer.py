from typing import Dict, Any, List, Optional
import duckdb

class Materializer:
    @staticmethod
    def create_wide_table(
        con: duckdb.DuckDBPyConnection,
        target_name: str,
        fact_table: str,
        dimension_joins: List[Dict[str, str]] # [{"dim_table": "dim_user", "on": "fact.user_id = dim_user.id", "select_cols": ["dim_user.age", "dim_user.city"]}]
    ) -> Dict[str, Any]:
        """
        Merge fact table and multiple dimension tables into a single analytical wide table.
        """
        join_clauses = []
        dim_selects = []

        for j in dimension_joins:
            dim_tab = j["dim_table"]
            on_clause = j["on"]
            join_clauses.append(f"LEFT JOIN {dim_tab} ON {on_clause}")
            for c in j.get("select_cols", []):
                dim_selects.append(c)

        dim_str = (", " + ", ".join(dim_selects)) if dim_selects else ""
        sql = f"""
        CREATE OR REPLACE TABLE {target_name} AS
        SELECT {fact_table}.*{dim_str}
        FROM {fact_table}
        {' '.join(join_clauses)}
        """

        con.execute(sql)
        row_count = con.execute(f"SELECT count(*) FROM {target_name}").fetchone()[0]

        return {
            "wide_table_name": target_name,
            "row_count": row_count,
            "status": "SUCCESS"
        }
