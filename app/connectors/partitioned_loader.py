import concurrent.futures
from typing import List, Optional
import pyarrow as pa
from app.connectors.factory import ConnectorFactory

class PartitionedLoader:
    """Loads massive datasets in parallel across partitions into an aggregated Arrow Table."""

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
        connector = ConnectorFactory.get_connector(conn_str)
        return connector.fetch_to_arrow(
            query_or_table=query_or_table,
            filter_sql=filter_sql,
            select_cols=select_cols,
            partition_col=partition_col,
            num_partitions=num_partitions,
            limit=limit
        )
