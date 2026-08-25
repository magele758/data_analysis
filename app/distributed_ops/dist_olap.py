from typing import List, Dict, Any, Optional
import duckdb
import pyarrow as pa

class DistributedOLAP:
    """High-performance multi-dimensional In-Memory OLAP aggregator."""

    @classmethod
    def aggregate(
        cls,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
        dimensions: List[str],
        metrics: List[str],
        agg_funcs: Optional[List[str]] = None,
        filters: Optional[str] = None,
        rollup: bool = False,
        cube: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = 1000
    ) -> pa.Table:
        funcs = agg_funcs or ["SUM" for _ in metrics]
        agg_exprs = []
        for m, f in zip(metrics, funcs):
            agg_exprs.append(f'{f.upper()}("{m}") AS "{m}_{f.lower()}"')
        
        dim_clause = ", ".join([f'"{d}"' for d in dimensions]) if dimensions else ""
        select_clause = ", ".join(filter(None, [dim_clause, ", ".join(agg_exprs)]))

        sql = f"SELECT {select_clause} FROM {table_name}"
        if filters:
            sql += f" WHERE {filters}"

        if dimensions:
            if cube:
                sql += f" GROUP BY CUBE ({dim_clause})"
            elif rollup:
                sql += f" GROUP BY ROLLUP ({dim_clause})"
            else:
                sql += f" GROUP BY {dim_clause}"

        if order_by:
            sql += f" ORDER BY {order_by}"
        elif metrics:
            sql += f" ORDER BY 2 DESC"

        if limit:
            sql += f" LIMIT {limit}"

        res = con.execute(sql).arrow()
        if isinstance(res, pa.RecordBatchReader):
            res = res.read_all()
        return res

    @classmethod
    def pivot_table(
        cls,
        con: duckdb.DuckDBPyConnection,
        table_name: str,
        rows: List[str],
        columns: str,
        values: str,
        agg_func: str = "SUM",
        filters: Optional[str] = None
    ) -> pa.Table:
        dist_sql = f'SELECT DISTINCT "{columns}" FROM {table_name} WHERE "{columns}" IS NOT NULL'
        if filters:
            dist_sql += f" AND ({filters})"
        distinct_vals = [str(r[0]) for r in con.execute(dist_sql).fetchall()]

        pivot_exprs = []
        for val in distinct_vals:
            safe_val = val.replace("'", "''")
            alias = f"{val}_{agg_func.lower()}"
            expr = f"{agg_func.upper()}(CASE WHEN \"{columns}\" = '{safe_val}' THEN \"{values}\" ELSE 0 END) AS \"{alias}\""
            pivot_exprs.append(expr)

        row_clause = ", ".join([f'"{r}"' for r in rows])
        select_clause = f"{row_clause}, " + ", ".join(pivot_exprs)
        
        sql = f"SELECT {select_clause} FROM {table_name}"
        if filters:
            sql += f" WHERE {filters}"
        sql += f" GROUP BY {row_clause} ORDER BY 1"

        res = con.execute(sql).arrow()
        if isinstance(res, pa.RecordBatchReader):
            res = res.read_all()
        return res
