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
        prefix = conn_str.split("://")[0].lower() if "://" in conn_str else "file"
        if prefix not in cls._registry:
            # Fallback check file existence
            return LocalFileConnector(conn_str)
        return cls._registry[prefix](conn_str)
