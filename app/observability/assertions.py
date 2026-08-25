from typing import Dict, List, Any, Optional
import duckdb
import time

class DataQualityAssertions:
    @staticmethod
    def expect_column_values_to_not_be_null(
        con: duckdb.DuckDBPyConnection,
        table: str,
        column: str
    ) -> Dict[str, Any]:
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        nulls = con.execute(f'SELECT count(*) FROM {table} WHERE "{column}" IS NULL').fetchone()[0]
        passed = (nulls == 0)
        return {
            "assertion": "expect_column_values_to_not_be_null",
            "column": column,
            "passed": passed,
            "total_records": total,
            "unexpected_count": nulls,
            "unexpected_percent": round((nulls / total * 100.0), 2) if total > 0 else 0.0
        }

    @staticmethod
    def expect_column_values_to_be_unique(
        con: duckdb.DuckDBPyConnection,
        table: str,
        column: str
    ) -> Dict[str, Any]:
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        distinct = con.execute(f'SELECT count(DISTINCT "{column}") FROM {table}').fetchone()[0]
        duplicates = total - distinct
        passed = (duplicates == 0)
        return {
            "assertion": "expect_column_values_to_be_unique",
            "column": column,
            "passed": passed,
            "total_records": total,
            "unexpected_count": duplicates,
            "unexpected_percent": round((duplicates / total * 100.0), 2) if total > 0 else 0.0
        }

    @staticmethod
    def expect_column_values_to_be_between(
        con: duckdb.DuckDBPyConnection,
        table: str,
        column: str,
        min_val: float,
        max_val: float
    ) -> Dict[str, Any]:
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        out_of_bounds = con.execute(
            f'SELECT count(*) FROM {table} WHERE "{column}" < {min_val} OR "{column}" > {max_val}'
        ).fetchone()[0]
        passed = (out_of_bounds == 0)
        return {
            "assertion": "expect_column_values_to_be_between",
            "column": column,
            "min_val": min_val,
            "max_val": max_val,
            "passed": passed,
            "total_records": total,
            "unexpected_count": out_of_bounds,
            "unexpected_percent": round((out_of_bounds / total * 100.0), 2) if total > 0 else 0.0
        }

    @staticmethod
    def expect_table_row_count_to_be_between(
        con: duckdb.DuckDBPyConnection,
        table: str,
        min_rows: int,
        max_rows: int
    ) -> Dict[str, Any]:
        total = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        passed = (min_rows <= total <= max_rows)
        return {
            "assertion": "expect_table_row_count_to_be_between",
            "min_rows": min_rows,
            "max_rows": max_rows,
            "actual_rows": total,
            "passed": passed
        }

    @classmethod
    def run_suite(
        cls,
        con: duckdb.DuckDBPyConnection,
        table: str,
        rules: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Production Consolidated Single-Pass Aggregation Execution:
        Compiles multiple rule metrics into a single SQL scan to optimize IO throughput.
        """
        if not rules:
            return {"table_name": table, "total_assertions": 0, "passed_assertions": 0, "data_health_score": 100.0, "assertion_results": []}

        start_t = time.time()
        
        # Build consolidated SELECT list
        agg_clauses = ["count(*) AS _total_count"]
        clause_map = []

        for idx, r in enumerate(rules):
            rtype = r.get("type")
            alias = f"_metric_{idx}"
            
            if rtype == "not_null":
                col = r["column"]
                agg_clauses.append(f'count(CASE WHEN "{col}" IS NULL THEN 1 END) AS {alias}')
                clause_map.append((idx, r, "not_null"))
            elif rtype == "unique":
                col = r["column"]
                agg_clauses.append(f'count(DISTINCT "{col}") AS {alias}')
                clause_map.append((idx, r, "unique"))
            elif rtype == "between":
                col = r["column"]
                min_v = r["min_val"]
                max_v = r["max_val"]
                agg_clauses.append(f'count(CASE WHEN "{col}" < {min_v} OR "{col}" > {max_v} THEN 1 END) AS {alias}')
                clause_map.append((idx, r, "between"))
            elif rtype == "row_count":
                # uses _total_count
                clause_map.append((idx, r, "row_count"))

        consolidated_sql = f"SELECT {', '.join(agg_clauses)} FROM {table}"
        row = con.execute(consolidated_sql).fetchone()
        cols = [d[0] for d in con.description]
        metrics_dict = dict(zip(cols, row))

        total_rows = metrics_dict.get("_total_count", 0)
        results = []
        passed_count = 0

        for idx, r, rtype in clause_map:
            alias = f"_metric_{idx}"
            val = metrics_dict.get(alias, 0)
            
            if rtype == "not_null":
                passed = (val == 0)
                unexpected = val
                results.append({
                    "assertion": "expect_column_values_to_not_be_null",
                    "column": r["column"],
                    "passed": passed,
                    "total_records": total_rows,
                    "unexpected_count": unexpected,
                    "unexpected_percent": round((unexpected / total_rows * 100.0), 2) if total_rows > 0 else 0.0
                })
            elif rtype == "unique":
                duplicates = total_rows - val
                passed = (duplicates == 0)
                results.append({
                    "assertion": "expect_column_values_to_be_unique",
                    "column": r["column"],
                    "passed": passed,
                    "total_records": total_rows,
                    "unexpected_count": duplicates,
                    "unexpected_percent": round((duplicates / total_rows * 100.0), 2) if total_rows > 0 else 0.0
                })
            elif rtype == "between":
                passed = (val == 0)
                results.append({
                    "assertion": "expect_column_values_to_be_between",
                    "column": r["column"],
                    "min_val": r["min_val"],
                    "max_val": r["max_val"],
                    "passed": passed,
                    "total_records": total_rows,
                    "unexpected_count": val,
                    "unexpected_percent": round((val / total_rows * 100.0), 2) if total_rows > 0 else 0.0
                })
            elif rtype == "row_count":
                passed = (r["min_rows"] <= total_rows <= r["max_rows"])
                results.append({
                    "assertion": "expect_table_row_count_to_be_between",
                    "min_rows": r["min_rows"],
                    "max_rows": r["max_rows"],
                    "actual_rows": total_rows,
                    "passed": passed
                })

            if passed:
                passed_count += 1

        total_rules = len(rules)
        health_score = round((passed_count / total_rules * 100.0), 1) if total_rules > 0 else 100.0
        duration_ms = round((time.time() - start_t) * 1000, 2)

        return {
            "table_name": table,
            "total_assertions": total_rules,
            "passed_assertions": passed_count,
            "failed_assertions": total_rules - passed_count,
            "data_health_score": health_score,
            "all_passed": (passed_count == total_rules),
            "scan_duration_ms": duration_ms,
            "assertion_results": results
        }
