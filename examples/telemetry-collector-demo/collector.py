import uuid
import time
from fastapi import APIRouter, Request, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from event_store import get_event_store

router = APIRouter(prefix="/api/v1/collect", tags=["Telemetry & Event Collector"])

class EventItem(BaseModel):
    event_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    event_type: str = "custom"
    event_name: str
    service_name: Optional[str] = "web-client"
    page_url: Optional[str] = None
    page_path: Optional[str] = "/"
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    screen_resolution: Optional[str] = None
    language: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    breadcrumbs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[str] = None
    timestamp_ms: Optional[int] = None

class BatchEventRequest(BaseModel):
    events: List[EventItem]

@router.post("/events")
async def collect_events(payload: BatchEventRequest, request: Request):
    """
    Ingest batch events from OpenTracker frontend SDK or OpenTelemetry HTTP exporter.
    """
    store = get_event_store()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now_ms = int(time.time() * 1000)

    ua = request.headers.get("user-agent", "")
    traceparent = request.headers.get("traceparent")

    processed = []
    for ev in payload.events:
        d = ev.model_dump()
        if not d.get("event_id"):
            d["event_id"] = "ev_" + uuid.uuid4().hex[:16]
        if not d.get("trace_id"):
            d["trace_id"] = uuid.uuid4().hex
        if not d.get("span_id"):
            d["span_id"] = uuid.uuid4().hex[:16]
        if not d.get("created_at"):
            d["created_at"] = now_iso
        if not d.get("timestamp_ms"):
            d["timestamp_ms"] = now_ms
        if not d.get("user_agent"):
            d["user_agent"] = ua
        if traceparent and not d.get("parent_span_id"):
            parts = traceparent.split("-")
            if len(parts) >= 3:
                d["trace_id"] = parts[1]
                d["parent_span_id"] = parts[2]
        processed.append(d)

    store.insert_events(processed)
    return {"status": "ok", "received_count": len(processed)}

@router.get("/realtime")
async def get_realtime_stream(limit: int = Query(50, ge=1, le=200)):
    """
    Fetch the latest real-time events from the in-memory RingBuffer.
    """
    store = get_event_store()
    events = store.get_realtime_events(limit=limit)
    return {"status": "ok", "total": len(events), "events": events}
