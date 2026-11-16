from typing import Dict, Type

import pyarrow as pa
from app.connectors.base import BaseConnector
from app.connectors.postgres import PostgresConnector
from app.connectors.mysql import MySQLConnector
from app.connectors.mssql import MSSQLConnector
from app.connectors.local import LocalFileConnector
from app.connectors.mongodb import MongoDBConnector


class ConnectorFactory:
    """Factory to instantiate corresponding DB connector by connection URI."""
    
    _registry: Dict[str, Type[BaseConnector]] = {
        "postgresql": PostgresConnector,
        "postgres": PostgresConnector,
        "mongodb": MongoDBConnector,
        "mongodb+srv": MongoDBConnector,
        "mysql": MySQLConnector,
        "mssql": MSSQLConnector,
        "sqlserver": MSSQLConnector,
        "sqlite": LocalFileConnector,
        "duckdb": LocalFileConnector,
        "file": LocalFileConnector,
    }

    @classmethod
    def get_connector(cls, conn_str: str) -> BaseConnector:
        if not isinstance(conn_str, str) or not conn_str.strip():
            raise ValueError("Connection string must be a non-empty string")
        text = conn_str.strip()
        if "://" not in text:
            return LocalFileConnector(text)
        prefix = text.split("://", 1)[0].lower()
        connector_cls = cls._registry.get(prefix)
        if connector_cls is None:
            known = ", ".join(sorted(cls._registry))
            raise ValueError(
                f"Unsupported connection scheme {prefix!r}. Supported schemes: {known}. "
                "Pass a local filesystem path without a scheme to read a file."
            )
        return connector_cls(text)


def read_source(conn_str: str, query_or_table: str, *, mongo_filter=None, **options) -> tuple[pa.Table, str]:
    """Shared HTTP/MCP dispatch. Only MongoDB accepts a native document filter."""
    connector = ConnectorFactory.get_connector(conn_str)
    if mongo_filter is not None:
        if not isinstance(connector, MongoDBConnector):
            raise ValueError("mongo_filter is only supported for MongoDB sources")
        options["mongo_filter"] = mongo_filter
    return connector.fetch_to_arrow(query_or_table, **options), connector.source_label
