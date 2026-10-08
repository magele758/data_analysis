from typing import Any, Dict, List, Optional

import duckdb

from app.engine.evidence import Stopwatch, evidence
from app.engine.sql_guard import safe_ident, safe_predicate, safe_table_ref

_ALLOWED_AGG = {"SUM", "AVG", "COUNT", "MIN", "MAX"}


class DistributedDriverAnalysis:
    """Hierarchical fluctuation breakdown.

    SUM metrics use an additive contribution that closes: at every level the
    child diffs sum to the parent diff. That is not a Shapley value. A ratio of
    rate and volume uses a Laspeyres split (volume, rate, interaction) and is
    labeled as such.
    """

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
        top_k: int = 5,
        rate_col: Optional[str] = None,
        volume_col: Optional[str] = None,
    ) -> Dict[str, Any]:
        clock = Stopwatch()
        if rate_col and volume_col:
            return cls._laspeyres(
                con, table_name, target_metric, dimension_path,
                base_filter, current_filter, top_k, rate_col, volume_col, clock,
            )

        func = agg_func.upper()
        if func not in _ALLOWED_AGG:
            raise ValueError(f"Unsupported aggregation function '{agg_func}'")
        table_ref = safe_table_ref(table_name)
        metric_col = safe_ident(target_metric)
        base_filter = safe_predicate(base_filter)
        current_filter = safe_predicate(current_filter)

        base_total_sql = f"SELECT {func}({metric_col}) FROM {table_ref} WHERE {base_filter}"
        curr_total_sql = f"SELECT {func}({metric_col}) FROM {table_ref} WHERE {current_filter}"
        base_total = float(con.execute(base_total_sql).fetchone()[0] or 0.0)
        curr_total = float(con.execute(curr_total_sql).fetchone()[0] or 0.0)
        diff_total = curr_total - base_total
        growth_rate = (diff_total / abs(base_total)) * 100 if base_total != 0 else 0.0

        method = "additive_contribution" if func == "SUM" else "level_comparison"
        caveats: List[str] = [
            "orderings_used is 1. The drill follows the caller dimension order. Sun-Shapley across permutations is not computed."
        ]
        if func != "SUM":
            caveats.append(
                f"{func} is not an additive partition. contribution_ratio is a level comparison, not a closed breakdown."
            )

        hierarchy = []
        sqls = [base_total_sql, curr_total_sql]
        for depth, dim in enumerate(dimension_path):
            current_dims = dimension_path[: depth + 1]
            dim_cols = ", ".join(safe_ident(d) for d in current_dims)
            join_cond = " AND ".join(
                f"c.{safe_ident(d)} IS NOT DISTINCT FROM b.{safe_ident(d)}" for d in current_dims
            )
            coalesce_cols = ", ".join(
                f"COALESCE(c.{safe_ident(d)}, b.{safe_ident(d)}) AS {safe_ident(d)}"
                for d in current_dims
            )
            sql = f"""
            WITH base_agg AS (
                SELECT {dim_cols}, {func}({metric_col}) AS base_val
                FROM {table_ref}
                WHERE {base_filter}
                GROUP BY {dim_cols}
            ),
            curr_agg AS (
                SELECT {dim_cols}, {func}({metric_col}) AS curr_val
                FROM {table_ref}
                WHERE {current_filter}
                GROUP BY {dim_cols}
            )
            SELECT {coalesce_cols},
                   COALESCE(b.base_val, 0) AS base_v,
                   COALESCE(c.curr_val, 0) AS curr_v,
                   COALESCE(c.curr_val, 0) - COALESCE(b.base_val, 0) AS diff_v
            FROM curr_agg c
            FULL OUTER JOIN base_agg b ON {join_cond}
            ORDER BY ABS(diff_v) DESC
            """
            sqls.append(sql)
            rows = con.execute(sql).fetchall()
            layer_items = []
            for row in rows:
                labels = [str(row[i]) for i in range(len(current_dims))]
                bv, cv, dv = float(row[-3]), float(row[-2]), float(row[-1])
                ratio = (dv / diff_total) if diff_total != 0 else 0.0
                layer_items.append({
                    "dimension": dim,
                    "dimension_value": labels[-1] if len(labels) == 1 else " / ".join(labels),
                    "dimension_path": dict(zip(current_dims, labels)),
                    "base_value": round(bv, 2),
                    "current_value": round(cv, 2),
                    "diff_value": round(dv, 2),
                    "contribution_ratio": round(ratio, 4),
                    "contribution_percentage": round(ratio * 100, 2),
                    "is_positive_driver": dv > 0,
                })
            diff_sum = round(sum(item["diff_value"] for item in layer_items), 2)
            closes = func == "SUM" and abs(diff_sum - round(diff_total, 2)) < 0.05
            if func == "SUM" and not closes:
                caveats.append(f"Level '{dim}' diff sum {diff_sum} does not match total diff {round(diff_total, 2)}.")
            hierarchy.append({
                "dimension_level": dim,
                "all_branches_count": len(layer_items),
                "diff_sum": diff_sum,
                "closes": closes,
                "top_positive_drivers": [item for item in layer_items if item["diff_value"] > 0][:top_k],
                "top_negative_drivers": [item for item in layer_items if item["diff_value"] < 0][:top_k],
                "branches": layer_items[: top_k * 2],
            })

        return {
            "target_metric": target_metric,
            "method": method,
            "base_total": round(base_total, 2),
            "current_total": round(curr_total, 2),
            "diff_total": round(diff_total, 2),
            "growth_rate_pct": round(growth_rate, 2),
            "orderings_used": 1,
            "hierarchy": hierarchy,
            "evidence": evidence(
                operator="driver_attribution_analysis",
                method=method,
                sql=sqls,
                duration_ms=clock.ms(),
                caveats=caveats,
            ),
        }

    @classmethod
    def _laspeyres(
        cls, con, table_name, target_metric, dimension_path,
        base_filter, current_filter, top_k, rate_col, volume_col, clock,
    ) -> Dict[str, Any]:
        """Δ(rate*volume) = p0*Δq + q0*Δp + Δp*Δq, summed over the first dimension."""
        if not dimension_path:
            raise ValueError("Laspeyres decomposition requires a dimension")
        dim = dimension_path[0]
        table_ref = safe_table_ref(table_name)
        rate = safe_ident(rate_col)
        volume = safe_ident(volume_col)
        dim_sql = safe_ident(dim)
        base_filter = safe_predicate(base_filter)
        current_filter = safe_predicate(current_filter)
        sql = f"""
        WITH base_agg AS (
            SELECT {dim_sql} AS dim_val,
                   SUM({rate} * {volume}) / NULLIF(SUM({volume}), 0) AS p0,
                   SUM({volume}) AS q0,
                   SUM({rate} * {volume}) AS v0
            FROM {table_ref} WHERE {base_filter} GROUP BY 1
        ),
        curr_agg AS (
            SELECT {dim_sql} AS dim_val,
                   SUM({rate} * {volume}) / NULLIF(SUM({volume}), 0) AS p1,
                   SUM({volume}) AS q1,
                   SUM({rate} * {volume}) AS v1
            FROM {table_ref} WHERE {current_filter} GROUP BY 1
        )
        SELECT COALESCE(c.dim_val, b.dim_val),
               COALESCE(b.v0, 0), COALESCE(c.v1, 0),
               COALESCE(b.p0, 0), COALESCE(c.p1, 0),
               COALESCE(b.q0, 0), COALESCE(c.q1, 0)
        FROM curr_agg c
        FULL OUTER JOIN base_agg b ON c.dim_val IS NOT DISTINCT FROM b.dim_val
        """
        rows = con.execute(sql).fetchall()
        items = []
        base_total = curr_total = 0.0
        for dim_val, v0, v1, p0, p1, q0, q1 in rows:
            v0, v1, p0, p1, q0, q1 = map(float, (v0, v1, p0, p1, q0, q1))
            volume_effect = p0 * (q1 - q0)
            rate_effect = q0 * (p1 - p0)
            interaction = (p1 - p0) * (q1 - q0)
            items.append({
                "dimension": dim,
                "dimension_value": str(dim_val),
                "base_value": round(v0, 2),
                "current_value": round(v1, 2),
                "diff_value": round(v1 - v0, 2),
                "volume_effect": round(volume_effect, 2),
                "rate_effect": round(rate_effect, 2),
                "interaction_effect": round(interaction, 2),
                "structure_effect": round(interaction, 2),
                "is_positive_driver": (v1 - v0) > 0,
            })
            base_total += v0
            curr_total += v1
        diff_total = curr_total - base_total
        for item in items:
            ratio = (item["diff_value"] / diff_total) if diff_total else 0.0
            item["contribution_ratio"] = round(ratio, 4)
            item["contribution_percentage"] = round(ratio * 100, 2)
        items.sort(key=lambda it: abs(it["diff_value"]), reverse=True)
        return {
            "target_metric": target_metric,
            "method": "laspeyres_rate_volume",
            "base_total": round(base_total, 2),
            "current_total": round(curr_total, 2),
            "diff_total": round(diff_total, 2),
            "growth_rate_pct": round((diff_total / abs(base_total)) * 100, 2) if base_total else 0.0,
            "orderings_used": 1,
            "hierarchy": [{
                "dimension_level": dim,
                "all_branches_count": len(items),
                "diff_sum": round(sum(it["diff_value"] for it in items), 2),
                "closes": abs(sum(it["diff_value"] for it in items) - diff_total) < 0.05,
                "top_positive_drivers": [it for it in items if it["diff_value"] > 0][:top_k],
                "top_negative_drivers": [it for it in items if it["diff_value"] < 0][:top_k],
                "branches": items[: top_k * 2],
            }],
            "evidence": evidence(
                operator="driver_attribution_analysis",
                method="laspeyres_rate_volume",
                sql=[sql],
                duration_ms=clock.ms(),
                caveats=[
                    "Laspeyres split is an accounting identity for rate x volume, not a causal effect.",
                    "structure_effect is the price-volume cross term. orderings_used is 1: only the first dimension is split, and Sun-Shapley is not computed.",
                ],
            ),
        }
