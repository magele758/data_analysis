from typing import Dict, Any, List, Optional
import duckdb
from app.engine.sql_guard import safe_ident, safe_predicate, safe_table_ref

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
        fact_cols = [row[0] for row in con.execute(f"DESCRIBE {fact_ref}").fetchall()]
        used_names = set(fact_cols)

        join_clauses = []
        dim_selects = []

        for j in dimension_joins:
            if "dim_table" not in j or "on" not in j:
                raise ValueError("dimension join requires 'dim_table' and 'on'")
            dim_ref = safe_table_ref(j["dim_table"])
            dim_bare = j["dim_table"].split(".")[-1]
            on_clause = safe_predicate(j["on"])
            join_clauses.append(f"LEFT JOIN {dim_ref} ON {on_clause}")
            for c in j.get("select_cols", []):
                # qualified column: "table"."col" or bare "col"
                quoted = safe_table_ref(c)
                bare = c.split(".")[-1]
                alias = bare
                if alias in used_names:
                    alias = f"{dim_bare}_{bare}"
                    suffix = 2
                    while alias in used_names:
                        alias = f"{dim_bare}_{bare}_{suffix}"
                        suffix += 1
                    dim_selects.append(f"{quoted} AS {safe_ident(alias)}")
                else:
                    dim_selects.append(quoted)
                used_names.add(alias)

        dim_str = (", " + ", ".join(dim_selects)) if dim_selects else ""
        sql = f"""
        CREATE OR REPLACE TABLE {target_ref} AS
        SELECT {fact_ref}.*{dim_str}
        FROM {fact_ref}
        {' '.join(join_clauses)}
        """

        con.execute(sql)
        row_count = con.execute(f"SELECT count(*) FROM {target_ref}").fetchone()[0]
        columns = [row[0] for row in con.execute(f"DESCRIBE {target_ref}").fetchall()]

        return {
            "wide_table_name": target_name,
            "row_count": row_count,
            "columns": columns,
            "status": "SUCCESS"
        }
