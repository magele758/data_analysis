from typing import Dict, Any, List, Optional
import duckdb
from app.engine.sql_guard import safe_predicate, safe_table_ref

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
        target_ref = safe_table_ref(target_name)
        fact_ref = safe_table_ref(fact_table)

        join_clauses = []
        dim_selects = []

        for j in dimension_joins:
            dim_ref = safe_table_ref(j["dim_table"])
            on_clause = safe_predicate(j["on"])
            join_clauses.append(f"LEFT JOIN {dim_ref} ON {on_clause}")
            for c in j.get("select_cols", []):
                # qualified column: "table"."col" or bare "col"
                dim_selects.append(safe_table_ref(c))

        dim_str = (", " + ", ".join(dim_selects)) if dim_selects else ""
        sql = f"""
        CREATE OR REPLACE TABLE {target_ref} AS
        SELECT {fact_ref}.*{dim_str}
        FROM {fact_ref}
        {' '.join(join_clauses)}
        """

        con.execute(sql)
        row_count = con.execute(f"SELECT count(*) FROM {target_ref}").fetchone()[0]

        return {
            "wide_table_name": target_name,
            "row_count": row_count,
            "status": "SUCCESS"
        }
