import os
from typing import List, Optional
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

    # ----------------- Security: API key auth -----------------
    # Comma-separated list of accepted keys. Parsed via api_key_list, not as a
    # JSON list, so DATA_AGENT_API_KEYS=key1,key2 works from a plain .env file.
    API_KEYS: str = ""
    # When True (default) the app refuses to start unless API_KEYS is non-empty.
    # Set to False ONLY for trusted local dev on a loopback-bound port.
    REQUIRE_AUTH: bool = True

    # ----------------- Security: CORS -----------------
    # Explicit origins only. "*" together with credentials is rejected by browsers
    # and is not accepted here.
    CORS_ALLOW_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # ----------------- Observability -----------------
    LOG_LEVEL: str = "INFO"

    # Optional Ray merge of Pearson sufficient statistics. Off keeps one DuckDB scan.
    RAY_ENABLED: bool = False
    RAY_ADDRESS: str = ""
    RAY_MIN_ROWS: int = 1_000_000
    RAY_PARTITIONS: int = 0

    # Optional OpenAI-compatible endpoint for insight order. Empty keeps severity order.
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: float = 3.0

    @property
    def api_key_list(self) -> List[str]:
        return [k.strip() for k in self.API_KEYS.split(",") if k.strip()]

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

settings = Settings()
