import time
import uuid
import threading
from typing import Dict, Optional, Any, List
import duckdb
import pyarrow as pa
from app.config import settings

class DatasetMeta:
    def __init__(self, name: str, arrow_table: pa.Table, source_info: Optional[Dict[str, Any]] = None):
        self.name = name
        if isinstance(arrow_table, pa.RecordBatchReader):
            arrow_table = arrow_table.read_all()
        self.table = arrow_table
        self.row_count = len(arrow_table)
        self.column_count = len(arrow_table.schema)
        self.column_names = arrow_table.column_names
        self.memory_bytes = arrow_table.nbytes
        self.loaded_at = time.time()
        self.source_info = source_info or {}

class SessionContext:
    """Isolated in-memory session holding DuckDB connection and loaded Arrow tables."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.last_accessed_at = time.time()
        self.datasets: Dict[str, DatasetMeta] = {}
        self._con = duckdb.connect(":memory:")
        
        # Configure DuckDB performance settings
        self._con.execute(f"SET memory_limit = '{settings.DUCKDB_MEMORY_LIMIT}'")
        self._con.execute(f"SET threads = {settings.DUCKDB_THREADS}")
        self._lock = threading.Lock()

    def touch(self):
        self.last_accessed_at = time.time()

    def is_expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.last_accessed_at) > ttl_seconds

    def register_dataset(self, name: str, table: Any, source_info: Optional[Dict[str, Any]] = None):
        if isinstance(table, pa.RecordBatchReader):
            table = table.read_all()
        with self._lock:
            self.touch()
            # Register arrow table directly as zero-copy in-memory view
            self._con.register(name, table)
            meta = DatasetMeta(name, table, source_info)
            self.datasets[name] = meta
            return meta

    def get_dataset_meta(self, name: str) -> Optional[DatasetMeta]:
        self.touch()
        return self.datasets.get(name)

    def execute_sql(self, sql: str, limit: Optional[int] = None) -> pa.Table:
        with self._lock:
            self.touch()
            clean_sql = sql.strip().rstrip(";")
            if limit and "LIMIT" not in clean_sql.upper():
                clean_sql += f" LIMIT {limit}"
            res = self._con.execute(clean_sql)
            tbl = res.arrow()
            if isinstance(tbl, pa.RecordBatchReader):
                tbl = tbl.read_all()
            return tbl

    def get_duckdb_conn(self) -> duckdb.DuckDBPyConnection:
        self.touch()
        return self._con

    def close(self):
        with self._lock:
            try:
                self._con.close()
            except Exception:
                pass
            self.datasets.clear()

class SessionManager:
    """Singleton manager for multi-tenant in-memory analytical sessions with auto TTL eviction."""
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SessionManager, cls).__new__(cls)
                cls._instance._sessions: Dict[str, SessionContext] = {}
                cls._instance._start_cleanup_thread()
            return cls._instance

    def get_or_create_session(self, session_id: Optional[str] = None) -> SessionContext:
        with self._lock:
            sid = session_id or str(uuid.uuid4())
            if sid not in self._sessions:
                self._sessions[sid] = SessionContext(sid)
            else:
                self._sessions[sid].touch()
            return self._sessions[sid]

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess:
                sess.touch()
            return sess

    def drop_session(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                sess = self._sessions.pop(session_id)
                sess.close()
                return True
            return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "session_id": sid,
                    "created_at": sess.created_at,
                    "last_accessed_at": sess.last_accessed_at,
                    "datasets": list(sess.datasets.keys())
                }
                for sid, sess in self._sessions.items()
            ]

    def _cleanup_expired_sessions(self):
        with self._lock:
            now = time.time()
            expired_ids = [
                sid for sid, sess in self._sessions.items()
                if sess.is_expired(settings.SESSION_TTL_SECONDS)
            ]
            for sid in expired_ids:
                sess = self._sessions.pop(sid)
                sess.close()

    def _start_cleanup_thread(self):
        def _loop():
            while True:
                time.sleep(60)
                try:
                    self._cleanup_expired_sessions()
                except Exception:
                    pass

        t = threading.Thread(target=_loop, daemon=True, name="SessionCleanerThread")
        t.start()
