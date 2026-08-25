from typing import Dict, List, Any, Optional
import duckdb

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
        """Run a full battery of data quality assertions."""
        results = []
        passed_count = 0

        for r in rules:
            rtype = r.get("type")
            res = {}
            if rtype == "not_null":
                res = cls.expect_column_values_to_not_be_null(con, table, r["column"])
            elif rtype == "unique":
                res = cls.expect_column_values_to_be_unique(con, table, r["column"])
            elif rtype == "between":
                res = cls.expect_column_values_to_be_between(con, table, r["column"], r["min_val"], r["max_val"])
            elif rtype == "row_count":
                res = cls.expect_table_row_count_to_be_between(con, table, r["min_rows"], r["max_rows"])

            if res.get("passed"):
                passed_count += 1
            results.append(res)

        total_rules = len(rules)
        health_score = round((passed_count / total_rules * 100.0), 1) if total_rules > 0 else 100.0

        return {
            "table_name": table,
            "total_assertions": total_rules,
            "passed_assertions": passed_count,
            "failed_assertions": total_rules - passed_count,
            "data_health_score": health_score,
            "all_passed": (passed_count == total_rules),
            "assertion_results": results
        }
