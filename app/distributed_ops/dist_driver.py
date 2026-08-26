from typing import List, Dict, Any, Optional
import duckdb

from app.engine.sql_guard import safe_ident, safe_table_ref, safe_predicate

_ALLOWED_AGG = {"SUM", "AVG", "COUNT", "MIN", "MAX"}

class DistributedDriverAnalysis:
    """Multi-dimensional Indicator Fluctuation Attribution & Shapley Driver Drill-Down Engine."""

    @classmethod
    def analyze_driver(
        cls,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
        target_metric: str,
        dimension_path: List[str],
        base_filter: str,
        current_filter: str,
        agg_func: str = "SUM",
        top_k: int = 5
    ) -> Dict[str, Any]:
        func = agg_func.upper()
        if func not in _ALLOWED_AGG:
            raise ValueError(f"Unsupported aggregation function '{agg_func}'")
        table_name = safe_table_ref(table_name)
        metric_col = safe_ident(target_metric)
        base_filter = safe_predicate(base_filter)
        current_filter = safe_predicate(current_filter)

        base_total_sql = f'SELECT {func}({metric_col}) FROM {table_name} WHERE {base_filter}'
        curr_total_sql = f'SELECT {func}({metric_col}) FROM {table_name} WHERE {current_filter}'

        base_total = con.execute(base_total_sql).fetchone()[0] or 0.0
        curr_total = con.execute(curr_total_sql).fetchone()[0] or 0.0
        diff_total = float(curr_total - base_total)
        growth_rate = (diff_total / abs(base_total)) * 100 if base_total != 0 else 0.0

        attribution_hierarchy = []

        current_dims = []
        for dim in dimension_path:
            current_dims.append(dim)
            dim_col = safe_ident(dim)
            dim_cols = ", ".join([safe_ident(d) for d in current_dims])
            join_cond = " AND ".join([f'c.{safe_ident(d)} = b.{safe_ident(d)}' for d in current_dims])

            sql = f"""
            WITH base_agg AS (
                SELECT {dim_cols}, {func}({metric_col}) AS base_val
                FROM {table_name}
                WHERE {base_filter}
                GROUP BY {dim_cols}
            ),
            curr_agg AS (
                SELECT {dim_cols}, {func}({metric_col}) AS curr_val
                FROM {table_name}
                WHERE {current_filter}
                GROUP BY {dim_cols}
            )
            SELECT
                COALESCE(c.{dim_col}, b.{dim_col}) AS dim_val,
                COALESCE(b.base_val, 0) AS base_v,
                COALESCE(c.curr_val, 0) AS curr_v,
                COALESCE(c.curr_val, 0) - COALESCE(b.base_val, 0) AS diff_v
            FROM curr_agg c
            FULL OUTER JOIN base_agg b ON {join_cond}
            ORDER BY ABS(diff_v) DESC
            """
            rows = con.execute(sql).fetchall()
            
            layer_items = []
            for r in rows:
                dim_v = str(r[0])
                bv = float(r[1])
                cv = float(r[2])
                dv = float(r[3])
                contrib_ratio = (dv / diff_total) if diff_total != 0 else 0.0
                layer_items.append({
                    "dimension": dim,
                    "dimension_value": dim_v,
                    "base_value": round(bv, 2),
                    "current_value": round(cv, 2),
                    "diff_value": round(dv, 2),
                    "contribution_ratio": round(contrib_ratio, 4),
                    "contribution_percentage": round(contrib_ratio * 100, 2),
                    "is_positive_driver": (dv > 0)
                })

            top_positive = [item for item in layer_items if item["diff_value"] > 0][:top_k]
            top_negative = [item for item in layer_items if item["diff_value"] < 0][:top_k]

            attribution_hierarchy.append({
                "dimension_level": dim,
                "all_branches_count": len(layer_items),
                "top_positive_drivers": top_positive,
                "top_negative_drivers": top_negative,
                "branches": layer_items[:top_k * 2]
            })

        return {
            "target_metric": target_metric,
            "base_total": round(base_total, 2),
            "current_total": round(curr_total, 2),
            "diff_total": round(diff_total, 2),
            "growth_rate_pct": round(growth_rate, 2),
            "hierarchy": attribution_hierarchy
        }
