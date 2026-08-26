import os
import json
import threading
from typing import List, Dict, Any, Optional
import duckdb
from ring_buffer import InvertedRingBuffer

class EventStore:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            os.makedirs("data", exist_ok=True)
            db_path = "data/analytics_events.duckdb"
        
        self.db_path = db_path
        self.con = duckdb.connect(database=self.db_path, read_only=False)
        self.ring_buffer = InvertedRingBuffer(capacity=1000)
        self._init_schema()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> "EventStore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db_path)
            return cls._instance

    def _init_schema(self):
        self.con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id VARCHAR PRIMARY KEY,
            trace_id VARCHAR,
            span_id VARCHAR,
            parent_span_id VARCHAR,
            session_id VARCHAR,
            user_id VARCHAR,
            event_type VARCHAR,
            event_name VARCHAR,
            service_name VARCHAR,
            page_url VARCHAR,
            page_path VARCHAR,
            page_title VARCHAR,
            referrer VARCHAR,
            user_agent VARCHAR,
            screen_resolution VARCHAR,
            language VARCHAR,
            properties JSON,
            breadcrumbs JSON,
            created_at TIMESTAMP,
            timestamp_ms BIGINT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration_seconds DOUBLE,
            event_count INTEGER,
            page_count INTEGER,
            entry_path VARCHAR,
            exit_path VARCHAR,
            is_bounce BOOLEAN
        );

        CREATE TABLE IF NOT EXISTS traces_spans (
            span_id VARCHAR PRIMARY KEY,
            trace_id VARCHAR,
            parent_span_id VARCHAR,
            name VARCHAR,
            service_name VARCHAR,
            status_code VARCHAR,
            duration_ms DOUBLE,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            attributes JSON
        );
        """)

    def insert_events(self, events: List[Dict[str, Any]]):
        if not events:
            return

        with self._lock:
            for ev in events:
                # Push to real-time ring buffer
                self.ring_buffer.push(ev)
                
                # Format properties and breadcrumbs
                props_json = json.dumps(ev.get("properties", {}))
                crumbs_json = json.dumps(ev.get("breadcrumbs", []))
                
                self.con.execute("""
                INSERT OR REPLACE INTO events VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """, [
                    ev.get("event_id"),
                    ev.get("trace_id"),
                    ev.get("span_id"),
                    ev.get("parent_span_id"),
                    ev.get("session_id"),
                    ev.get("user_id"),
                    ev.get("event_type"),
                    ev.get("event_name"),
                    ev.get("service_name", "web-client"),
                    ev.get("page_url"),
                    ev.get("page_path", "/"),
                    ev.get("page_title"),
                    ev.get("referrer"),
                    ev.get("user_agent"),
                    ev.get("screen_resolution"),
                    ev.get("language"),
                    props_json,
                    crumbs_json,
                    ev.get("created_at"),
                    ev.get("timestamp_ms", 0)
                ])

                # Record OTel Trace Span
                self.con.execute("""
                INSERT OR REPLACE INTO traces_spans VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """, [
                    ev.get("span_id"),
                    ev.get("trace_id"),
                    ev.get("parent_span_id"),
                    ev.get("event_name"),
                    ev.get("service_name", "frontend"),
                    "OK" if ev.get("event_type") != "error" else "ERROR",
                    ev.get("properties", {}).get("duration_ms", 0.0),
                    ev.get("created_at"),
                    ev.get("created_at"),
                    props_json
                ])

    def query(self, sql: str, params: Optional[list] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if params:
                df = self.con.execute(sql, params).df()
            else:
                df = self.con.execute(sql).df()
            return df.to_dict(orient="records")

    def get_realtime_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.ring_buffer.get_latest(limit)

def get_event_store() -> EventStore:
    return EventStore.get_instance()
