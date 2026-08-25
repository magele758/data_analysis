import math
from typing import Dict, Any, List, Optional
import pyarrow as pa
import duckdb
import numpy as np
from app.engine.schema_infer import SchemaInferencer, SemanticType

class DistributedEDA:
    """Distributed Single-Pass Sufficient Statistics Engine for Million/Billion Row Profiling."""

    @classmethod
    def profile_table(cls, con: duckdb.DuckDBPyConnection, table_name: str) -> Dict[str, Any]:
        total_rows = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        schema_map = SchemaInferencer.infer_table_schema(con.execute(f"SELECT * FROM {table_name} LIMIT 5000").arrow())

        column_reports = {}
        quality_penalties = 0

        for col_name, meta in schema_map.items():
            sem_t = meta["semantic_type"]
            phy_t = meta["physical_type"]
            
            null_distinct_sql = f"""
            SELECT 
                COUNT(*) - COUNT("{col_name}") AS null_cnt,
                COUNT(DISTINCT "{col_name}") AS distinct_cnt
            FROM {table_name}
            """
            null_cnt, dist_cnt = con.execute(null_distinct_sql).fetchone()
            null_rate = (null_cnt / max(1, total_rows)) * 100

            if null_rate > 30:
                quality_penalties += 10
            elif null_rate > 5:
                quality_penalties += 3

            report = {
                "column_name": col_name,
                "physical_type": phy_t,
                "semantic_type": sem_t,
                "total_rows": total_rows,
                "null_count": null_cnt,
                "null_percentage": round(null_rate, 2),
                "distinct_count": dist_cnt,
            }

            if sem_t == SemanticType.MEASURE.value:
                num_sql = f"""
                SELECT 
                    AVG("{col_name}") AS mean_val,
                    STDDEV_SAMP("{col_name}") AS std_val,
                    MIN("{col_name}") AS min_v,
                    MAX("{col_name}") AS max_v,
                    MEDIAN("{col_name}") AS p50,
                    QUANTILE_CONT("{col_name}", 0.25) AS p25,
                    QUANTILE_CONT("{col_name}", 0.75) AS p75,
                    QUANTILE_CONT("{col_name}", 0.95) AS p95,
                    QUANTILE_CONT("{col_name}", 0.99) AS p99,
                    SKEWNESS("{col_name}") AS skewness,
                    KURTOSIS("{col_name}") AS kurtosis
                FROM {table_name}
                WHERE "{col_name}" IS NOT NULL
                """
                row = con.execute(num_sql).fetchone()
                if row and row[0] is not None:
                    report.update({
                        "mean": round(float(row[0]), 4),
                        "std": round(float(row[1]) if row[1] is not None else 0.0, 4),
                        "min": round(float(row[2]), 4),
                        "max": round(float(row[3]), 4),
                        "quantiles": {
                            "p25": round(float(row[5]), 4) if row[5] is not None else None,
                            "p50": round(float(row[4]), 4) if row[4] is not None else None,
                            "p75": round(float(row[6]), 4) if row[6] is not None else None,
                            "p95": round(float(row[7]), 4) if row[7] is not None else None,
                            "p99": round(float(row[8]), 4) if row[8] is not None else None,
                        },
                        "skewness": round(float(row[9]), 4) if row[9] is not None else 0.0,
                        "kurtosis": round(float(row[10]), 4) if row[10] is not None else 0.0,
                    })
            elif sem_t == SemanticType.DIMENSION_CATEGORICAL.value:
                cat_sql = f"""
                SELECT "{col_name}" AS val, COUNT(*) AS cnt, ROUND(COUNT(*) * 100.0 / {total_rows}, 2) AS pct
                FROM {table_name}
                WHERE "{col_name}" IS NOT NULL
                GROUP BY 1
                ORDER BY cnt DESC
                LIMIT 10
                """
                top_cats = [
                    {"value": str(r[0]), "count": r[1], "percentage": r[2]}
                    for r in con.execute(cat_sql).fetchall()
                ]
                report["top_categories"] = top_cats

            column_reports[col_name] = report

        overall_quality_score = max(20, 100 - quality_penalties)

        return {
            "table_name": table_name,
            "total_rows": total_rows,
            "total_columns": len(schema_map),
            "quality_score": overall_quality_score,
            "columns": column_reports
        }
