from typing import Dict, Type
from app.connectors.base import BaseConnector
from app.connectors.postgres import PostgresConnector
from app.connectors.mysql import MySQLConnector
from app.connectors.mssql import MSSQLConnector
from app.connectors.local import LocalFileConnector

class ConnectorFactory:
    """Factory to instantiate corresponding DB connector by connection URI."""
    
    _registry: Dict[str, Type[BaseConnector]] = {
        "postgresql": PostgresConnector,
        "postgres": PostgresConnector,
        "mysql": MySQLConnector,
        "mssql": MSSQLConnector,
        "sqlserver": MSSQLConnector,
        "sqlite": LocalFileConnector,
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
