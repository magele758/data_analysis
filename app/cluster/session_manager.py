import re
import shutil
import tempfile
import time
import uuid
import threading
from typing import Dict, Optional, Any, List
import duckdb
import pyarrow as pa
from app.config import settings

_DATASET_NAME_RE = re.compile(r"[\x00-\x1f;\"]")

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
        slug = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:12] or "sess"
        self._temp_dir = tempfile.mkdtemp(prefix=f"duckdb-{slug}-")
        self._lock = threading.Lock()
        try:
            self._con = duckdb.connect(":memory:")
            # One session cannot claim the whole machine. Spill lands in temp_directory.
            session_limit = f"{int(settings.MAX_MEMORY_PER_SESSION_MB)}MB"
            self._con.execute(f"SET memory_limit = '{session_limit}'")
            self._con.execute(f"SET threads = {settings.DUCKDB_THREADS}")
            try:
                escaped = self._temp_dir.replace("'", "''")
                self._con.execute(f"SET temp_directory = '{escaped}'")
            except duckdb.Error:
                pass
            self.memory_limit = session_limit
        except Exception:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            raise

    def touch(self):
        self.last_accessed_at = time.time()

    def is_expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.last_accessed_at) > ttl_seconds

    def register_dataset(self, name: str, table: Any, source_info: Optional[Dict[str, Any]] = None):
        _validate_dataset_name(name)
        if isinstance(table, pa.RecordBatchReader):
            table = table.read_all()
        with self._lock:
            self.touch()
            new_bytes = int(getattr(table, "nbytes", 0) or 0)
            used = sum(
                meta.memory_bytes for key, meta in self.datasets.items() if key != name
            )
            limit_bytes = int(settings.MAX_MEMORY_PER_SESSION_MB) * 1024 * 1024
            if used + new_bytes > limit_bytes:
                raise ValueError(
                    f"Session '{self.session_id}' memory budget exceeded: "
                    f"{used + new_bytes} bytes > {limit_bytes} bytes "
                    f"({settings.MAX_MEMORY_PER_SESSION_MB} MB). "
                    "Sessions are process-local; extra workers do not share this budget."
                )
            # Register arrow table directly as zero-copy in-memory view
            self._con.register(name, table)
            meta = DatasetMeta(name, table, _redact_source(source_info))
            try:
                summary = self._con.execute(f"SUMMARIZE {_quote_dataset_name(name)}").fetchall()
                meta.summarize = [
                    {"column": r[0], "type": r[1], "approx_unique": r[4], "null_percentage": r[10]}
                    if len(r) > 10 else {"column": r[0]}
                    for r in summary
                ]
            except Exception:
                meta.summarize = None
            try:
                self._con.execute(f"ANALYZE {_quote_dataset_name(name)}")
                meta.stats_collected = True
            except Exception:
                # Views over Arrow often have no persistent-table statistics.
                meta.stats_collected = False
            self.datasets[name] = meta
            return meta

    def get_dataset_meta(self, name: str) -> Optional[DatasetMeta]:
        self.touch()
        return self.datasets.get(name)

    def execute_sql(self, sql: str, limit: Optional[int] = None) -> pa.Table:
        with self._lock:
            self.touch()
            clean_sql = sql.strip().rstrip(";")
            if limit is not None:
                if isinstance(limit, bool) or not isinstance(limit, int):
                    raise ValueError(f"limit must be a non-negative integer, got {limit!r}")
                if limit < 0:
                    raise ValueError("limit must be >= 0")
                if limit and not re.search(r"\bLIMIT\b", clean_sql, re.IGNORECASE):
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
            shutil.rmtree(self._temp_dir, ignore_errors=True)


def _validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
        raise ValueError("Invalid session_id: expected 1-128 non-blank characters")
    if any(ord(ch) < 32 for ch in session_id) or "/" in session_id or "\\" in session_id or ".." in session_id:
        raise ValueError(
            "Invalid session_id: slashes, control characters, and '..' are not allowed"
        )
    return session_id


def _validate_dataset_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip() or len(name) > 128 or _DATASET_NAME_RE.search(name):
        raise ValueError(
            f"Invalid dataset name {name!r}: use 1-128 characters without quotes, semicolons, or control characters"
        )
    return name


def _quote_dataset_name(name: str) -> str:
    _validate_dataset_name(name)
    return '"' + name + '"'


def _redact_source(source_info: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    info = dict(source_info or {})
    for key in ("conn_str", "connection_string", "password"):
        if key in info and isinstance(info[key], str):
            info[key] = "***"
    return info

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
            _validate_session_id(sid)
            if sid not in self._sessions:
                self._sessions[sid] = SessionContext(sid)
            else:
                self._sessions[sid].touch()
            return self._sessions[sid]

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        if session_id is not None:
            _validate_session_id(session_id)
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess:
                sess.touch()
            return sess

    def drop_session(self, session_id: str) -> bool:
        _validate_session_id(session_id)
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
