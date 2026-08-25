import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATA_AGENT_", case_sensitive=False)

    APP_NAME: str = "Data Analysis Service & Distributed Insight Engine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    
    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # MCP settings
    MCP_SERVER_NAME: str = "data-analysis-service"
    MCP_TRANSPORT: str = "stdio"
    MCP_SSE_PORT: int = 8001
    
    # In-memory session & TTL settings
    SESSION_TTL_SECONDS: int = 1800
    MAX_MEMORY_PER_SESSION_MB: int = 4096
    DUCKDB_MEMORY_LIMIT: str = "16GB"
    DUCKDB_THREADS: int = Field(default_factory=lambda: max(1, os.cpu_count() or 4))
    
    # Ray Cluster Settings
    ENABLE_RAY: bool = False
    RAY_ADDRESS: Optional[str] = None
    
    # Arrow Flight Server
    FLIGHT_HOST: str = "0.0.0.0"
    FLIGHT_PORT: int = 8815
    
    # CDC & Streaming Buffer
    RING_BUFFER_CAPACITY: int = 100000
    STREAM_BATCH_INTERVAL_MS: int = 500

settings = Settings()
