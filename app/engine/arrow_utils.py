import math
import pyarrow as pa
from typing import List, Dict, Any, Optional

class ArrowUtils:
    """Zero-copy Arrow Table manipulation and conversion utilities."""

    @staticmethod
    def df_to_records(df) -> List[Dict[str, Any]]:
        """DataFrame -> JSON-safe list of dicts.

        pandas turns SQL NULLs in numeric columns (and all-NULL columns) into
        float NaN, which json.dumps rejects ('Out of range float values are not
        JSON compliant'). Collapse every NaN/Inf to None so any downstream JSON
        response is safe regardless of how sparse the source table is.
        """
        records = df.to_dict(orient="records")
        for row in records:
            for key, val in row.items():
                if isinstance(val, float) and not math.isfinite(val):
                    row[key] = None
        return records

    @staticmethod
    def fetch_table(result) -> pa.Table:
        """Materialize a DuckDB execute() result.

        1.x exposed result.arrow(), sometimes as a reader. 2.0 removed arrow()
        and kept to_arrow_table(). Consume the result either way so the
        connection is not left with an unfinished query.
        """
        fetch = getattr(result, "to_arrow_table", None) or getattr(result, "arrow", None)
        if fetch is None:
            raise AttributeError("DuckDB result has neither to_arrow_table nor arrow")
        table = fetch()
        if isinstance(table, pa.RecordBatchReader):
            table = table.read_all()
        return table

    @staticmethod
    def table_to_compact_preview(table: Any, limit: int = 20) -> List[Dict[str, Any]]:
        if isinstance(table, pa.RecordBatchReader):
            table = table.read_all()
        sliced = table.slice(0, limit)
        return sliced.to_pylist()

    @staticmethod
    def split_into_partitions(table: pa.Table, num_partitions: int) -> List[pa.Table]:
        if num_partitions <= 1 or len(table) < num_partitions:
            return [table]
        chunk_size = (len(table) + num_partitions - 1) // num_partitions
        partitions = []
        for i in range(num_partitions):
            start = i * chunk_size
            if start >= len(table):
                break
            length = min(chunk_size, len(table) - start)
            partitions.append(table.slice(start, length))
        return partitions
