"""Standalone telemetry-collection demo (NOT part of the main analysis service).

Purpose: illustrate Path B's *source* — how browser/OTel telemetry can be
collected — and how those traces are then handed to the main data-analysis
service for processing. The main service deliberately does not collect telemetry
itself; it ingests trace data via its `import_traces` tool / `/api/v1/import/traces`
endpoint. This demo produces exactly that shape.

Run:
    cd examples/telemetry-collector-demo
    uvicorn demo_server:app --port 8100
Then open http://localhost:8100/ to generate events, and GET
http://localhost:8100/export to obtain a JSON payload you can feed to the main
service's import_traces (source=<saved file>) or /api/v1/import/traces.
"""

import json
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from collector import router as collector_router
from event_store import get_event_store

app = FastAPI(title="Telemetry Collector Demo")
app.include_router(collector_router)

_HERE = os.path.dirname(os.path.abspath(__file__))
app.mount("/sdk", StaticFiles(directory=os.path.join(_HERE, "browser-tracker"), html=True), name="sdk")


@app.get("/")
def index():
    return JSONResponse({
        "demo": "telemetry-collector",
        "note": "This is an optional demo, separate from the main analysis service.",
        "try": [
            "Open /sdk/ to load the browser tracker and generate events",
            "POST events to /api/v1/collect/events",
            "GET /export to get an import_traces-compatible payload",
        ],
    })


@app.get("/export")
def export_for_pipeline():
    """Dump collected events as an import_traces-compatible {"events": [...]} payload.

    Save this to a .json file and load it into the main service with
    import_traces(source="events.json", dataset_name="telemetry"), which lands it
    in an analytical session where the full MDS pipeline can operate on it.
    """
    store = get_event_store()
    rows = store.query("SELECT * FROM events ORDER BY timestamp_ms ASC")
    for r in rows:
        props = r.get("properties")
        if isinstance(props, str):
            try:
                r["properties"] = json.loads(props)
            except (ValueError, TypeError):
                r["properties"] = {}
    return {"events": rows}
