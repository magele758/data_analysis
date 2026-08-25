import abc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import pyarrow as pa

class ColumnInfo(BaseModel):
    name: str
    physical_type: str
    semantic_type: Optional[str] = None  # MEASURE, DIMENSION_CATEGORICAL, DIMENSION_TEMPORAL, IDENTIFIER, TEXT
    is_nullable: bool = True
    comment: Optional[str] = None

class TableSchema(BaseModel):
    table_name: str
    columns: List[ColumnInfo]
    estimated_rows: Optional[int] = None
    primary_keys: List[str] = []

class BaseConnector(abc.ABC):
    """Abstract Base Class for High-Performance DB Connectors."""

    def __init__(self, conn_str: str):
        self.conn_str = conn_str

    @abc.abstractmethod
    def test_connection(self) -> bool:
        """Test if the target database is reachable."""
        pass

    @abc.abstractmethod
    def list_tables(self) -> List[str]:
        """List all available tables and views in target DB."""
        pass

    @abc.abstractmethod
    def introspect_schema(self, table_name: str) -> TableSchema:
        """Retrieve column metadata and infer preliminary types."""
        pass

    @abc.abstractmethod
    def fetch_to_arrow(
        self,
        query_or_table: str,
        filter_sql: Optional[str] = None,
        select_cols: Optional[List[str]] = None,
        partition_col: Optional[str] = None,
        num_partitions: int = 1,
        limit: Optional[int] = None
    ) -> pa.Table:
        """Fetch records from source DB directly into PyArrow Table in parallel."""
        pass
