import json
from typing import Dict, Any, List, Optional
from app.storage.event_store import get_event_store

def get_trace_waterfall(trace_id: str) -> Dict[str, Any]:
    """
    Construct OpenTelemetry waterfall spans tree for a given trace_id.
    """
    store = get_event_store()
    sql = """
    SELECT 
        span_id, trace_id, parent_span_id, name, service_name, 
        status_code, duration_ms, start_time, attributes
    FROM traces_spans
    WHERE trace_id = ?
    ORDER BY start_time ASC
    """
    spans = store.query(sql, [trace_id])
    return {
        "trace_id": trace_id,
        "total_spans": len(spans),
        "spans": spans
    }

def get_session_action_replay(session_id: str) -> Dict[str, Any]:
    """
    Reconstruct chronological user interaction breadcrumbs for session replay.
    """
    store = get_event_store()
    sql = """
    SELECT 
        event_id, trace_id, event_type, event_name, page_path, page_url,
        properties, breadcrumbs, created_at, timestamp_ms
    FROM events
    WHERE session_id = ?
    ORDER BY timestamp_ms ASC
    """
    events = store.query(sql, [session_id])
    
    actions = []
    for ev in events:
        props = json.loads(ev["properties"]) if isinstance(ev["properties"], str) else ev["properties"]
        actions.append({
            "event_id": ev["event_id"],
            "event_type": ev["event_type"],
            "event_name": ev["event_name"],
            "page_path": ev["page_path"],
            "created_at": str(ev["created_at"]),
            "timestamp_ms": ev["timestamp_ms"],
            "properties": props or {}
        })

    return {
        "session_id": session_id,
        "action_count": len(actions),
        "timeline": actions
    }

def list_recent_sessions(limit: int = 20) -> List[Dict[str, Any]]:
    """
    List recent active user sessions with event counts and error flags.
    """
    store = get_event_store()
    sql = """
    SELECT 
        session_id,
        user_id,
        min(created_at) as start_time,
        max(created_at) as end_time,
        count(*) as event_count,
        count(CASE WHEN event_type = 'error' THEN 1 END) as error_count,
        min(page_path) as entry_path,
        max(page_path) as exit_path
    FROM events
    GROUP BY session_id, user_id
    ORDER BY max(created_at) DESC
    LIMIT ?
    """
    return store.query(sql, [limit])
