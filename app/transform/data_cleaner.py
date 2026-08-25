from typing import Dict, List, Any, Optional
import duckdb

class DataCleaner:
    @staticmethod
    def clean_table(
        con: duckdb.DuckDBPyConnection,
        source_table: str,
        target_table: str,
        dedup_keys: Optional[List[str]] = None,
        fillna_rules: Optional[Dict[str, Any]] = None, # col -> value or "MEAN", "MEDIAN", "MODE"
        outlier_clip_cols: Optional[Dict[str, Dict[str, float]]] = None # col -> {"min": 0, "max": 100}
    ) -> Dict[str, Any]:
        """
        Execute automated data cleaning pipeline and materialize into target_table.
        """
        # 1. Build SELECT expressions
        cols_info = con.execute(f"DESCRIBE {source_table}").fetchall()
        col_names = [r[0] for r in cols_info]

        select_exprs = []
        for col in col_names:
            expr = f'"{col}"'
            
            # Apply fillna
            if fillna_rules and col in fillna_rules:
                val = fillna_rules[col]
                if isinstance(val, (int, float)):
                    expr = f'COALESCE({expr}, {val})'
                elif isinstance(val, str):
                    if val.upper() == "MEAN":
                        mean_val = con.execute(f'SELECT avg("{col}") FROM {source_table}').fetchone()[0] or 0.0
                        expr = f'COALESCE({expr}, {mean_val})'
                    elif val.upper() == "MEDIAN":
                        med_val = con.execute(f'SELECT median("{col}") FROM {source_table}').fetchone()[0] or 0.0
                        expr = f'COALESCE({expr}, {med_val})'
                    else:
                        expr = f"COALESCE({expr}, '{val}')"

            # Apply clipping / winsorization
            if outlier_clip_cols and col in outlier_clip_cols:
                min_v = outlier_clip_cols[col].get("min")
                max_v = outlier_clip_cols[col].get("max")
                if min_v is not None and max_v is not None:
                    expr = f'CASE WHEN {expr} < {min_v} THEN {min_v} WHEN {expr} > {max_v} THEN {max_v} ELSE {expr} END'
                elif min_v is not None:
                    expr = f'CASE WHEN {expr} < {min_v} THEN {min_v} ELSE {expr} END'
                elif max_v is not None:
                    expr = f'CASE WHEN {expr} > {max_v} THEN {max_v} ELSE {expr} END'

            select_exprs.append(f'{expr} AS "{col}"')

        # 2. Build Query with Deduplication
        if dedup_keys:
            keys_str = ', '.join([f'"{k}"' for k in dedup_keys])
            clean_query = f"""
            WITH ranked AS (
                SELECT 
                    {', '.join(select_exprs)},
                    ROW_NUMBER() OVER (PARTITION BY {keys_str} ORDER BY (SELECT 1)) as _rn
                FROM {source_table}
            )
            SELECT * EXCLUDE (_rn) FROM ranked WHERE _rn = 1
            """
        else:
            clean_query = f"SELECT {', '.join(select_exprs)} FROM {source_table}"

        con.execute(f"CREATE OR REPLACE TABLE {target_table} AS {clean_query}")
        
        orig_count = con.execute(f"SELECT count(*) FROM {source_table}").fetchone()[0]
        new_count = con.execute(f"SELECT count(*) FROM {target_table}").fetchone()[0]

        return {
            "source_table": source_table,
            "target_table": target_table,
            "original_rows": orig_count,
            "cleaned_rows": new_count,
            "removed_duplicates": orig_count - new_count
        }
