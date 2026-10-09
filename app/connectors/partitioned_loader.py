import concurrent.futures
from typing import List, Optional
import pyarrow as pa
from app.connectors.factory import ConnectorFactory
from app.connectors.local import LocalFileConnector
from app.engine.sql_guard import safe_ident


class PartitionedLoader:
    """Load a dataset, splitting local files across hash buckets when asked.

    Database connectors keep ConnectorX ``partition_on`` (one scan, native ranges).
    Local files have no range API, so each bucket is a filtered read and the
    buckets are concatenated. Rows are not returned in source order.
    """

    @staticmethod
    def load_parallel(
        conn_str: str,
        query_or_table: str,
        partition_col: Optional[str] = None,
        num_partitions: int = 4,
        select_cols: Optional[List[str]] = None,
        filter_sql: Optional[str] = None,
        limit: Optional[int] = None
    ) -> pa.Table:
        if isinstance(num_partitions, bool) or not isinstance(num_partitions, int) or num_partitions < 1:
            raise ValueError(f"num_partitions must be an integer >= 1, got {num_partitions!r}")
        connector = ConnectorFactory.get_connector(conn_str)
        if (
            isinstance(connector, LocalFileConnector)
            and partition_col
            and num_partitions > 1
        ):
            if num_partitions > 32:
                raise ValueError("num_partitions for a local file must be <= 32")
            return PartitionedLoader._load_local_buckets(
                connector,
                query_or_table=query_or_table,
                partition_col=partition_col,
                num_partitions=num_partitions,
                select_cols=select_cols,
                filter_sql=filter_sql,
                limit=limit,
            )
        return connector.fetch_to_arrow(
            query_or_table=query_or_table,
            filter_sql=filter_sql,
            select_cols=select_cols,
            partition_col=partition_col,
            num_partitions=num_partitions,
            limit=limit
        )

    @staticmethod
    def _load_local_buckets(
        connector: LocalFileConnector,
        query_or_table: str,
        partition_col: str,
        num_partitions: int,
        select_cols: Optional[List[str]],
        filter_sql: Optional[str],
        limit: Optional[int],
    ) -> pa.Table:
        ident = safe_ident(partition_col)

        def one(bucket: int) -> pa.Table:
            pred = (
                f"((hash({ident}) % {num_partitions}) = {bucket}) OR "
                f"({ident} IS NULL AND hash({ident}) IS NULL AND {bucket} = 0)"
            )
            if filter_sql:
                pred = f"({filter_sql}) AND ({pred})"
            return connector.fetch_to_arrow(
                query_or_table=query_or_table,
                filter_sql=pred,
                select_cols=select_cols,
                limit=None,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_partitions) as pool:
            tables = list(pool.map(one, range(num_partitions)))
        merged = pa.concat_tables(tables)
        if limit is None:
            return merged
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError(f"limit must be a non-negative integer, got {limit!r}")
        return merged.slice(0, limit)
