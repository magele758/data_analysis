import pytest
import time
from fastapi.testclient import TestClient
from app.config import settings

settings.API_KEYS = "test-api-key"

from app.main import app
from app.storage.event_store import get_event_store
from app.operators.web_analytics.funnel import calculate_funnel
from app.operators.web_analytics.flow import calculate_user_flow
from app.operators.web_analytics.retention import calculate_retention
from app.operators.web_analytics.page_analytics import calculate_page_metrics
from app.operators.web_analytics.trace_replay import get_trace_waterfall, get_session_action_replay

client = TestClient(app, headers={"X-API-Key": "test-api-key"})

@pytest.fixture(autouse=True)
def setup_test_events():
    store = get_event_store()
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    now_ms = int(time.time() * 1000)

    # Insert synthetic user journeys
    events = [
        # User 1 completes full funnel
        {
            "event_id": "e_u1_1", "trace_id": "trace_100", "span_id": "span_101",
            "session_id": "sess_100", "user_id": "user_1", "event_type": "pageview",
            "event_name": "$pageview", "page_path": "/home", "created_at": now_iso, "timestamp_ms": now_ms
        },
        {
            "event_id": "e_u1_2", "trace_id": "trace_100", "span_id": "span_102",
            "session_id": "sess_100", "user_id": "user_1", "event_type": "custom",
            "event_name": "view_item", "page_path": "/products/1", "created_at": now_iso, "timestamp_ms": now_ms + 1000
        },
        {
            "event_id": "e_u1_3", "trace_id": "trace_100", "span_id": "span_103",
            "session_id": "sess_100", "user_id": "user_1", "event_type": "custom",
            "event_name": "add_to_cart", "page_path": "/cart", "created_at": now_iso, "timestamp_ms": now_ms + 2000
        },
        {
            "event_id": "e_u1_4", "trace_id": "trace_100", "span_id": "span_104",
            "session_id": "sess_100", "user_id": "user_1", "event_type": "custom",
            "event_name": "purchase_success", "page_path": "/checkout/success", "created_at": now_iso, "timestamp_ms": now_ms + 3000
        },
        # User 2 drops after add_to_cart
        {
            "event_id": "e_u2_1", "trace_id": "trace_200", "span_id": "span_201",
            "session_id": "sess_200", "user_id": "user_2", "event_type": "pageview",
            "event_name": "$pageview", "page_path": "/home", "created_at": now_iso, "timestamp_ms": now_ms
        },
        {
            "event_id": "e_u2_2", "trace_id": "trace_200", "span_id": "span_202",
            "session_id": "sess_200", "user_id": "user_2", "event_type": "custom",
            "event_name": "view_item", "page_path": "/products/2", "created_at": now_iso, "timestamp_ms": now_ms + 1000
        },
        {
            "event_id": "e_u2_3", "trace_id": "trace_200", "span_id": "span_203",
            "session_id": "sess_200", "user_id": "user_2", "event_type": "custom",
            "event_name": "add_to_cart", "page_path": "/cart", "created_at": now_iso, "timestamp_ms": now_ms + 2000
        },
        # User 3 error
        {
            "event_id": "e_u3_1", "trace_id": "trace_300", "span_id": "span_301",
            "session_id": "sess_300", "user_id": "user_3", "event_type": "error",
            "event_name": "$error", "page_path": "/cart", "created_at": now_iso, "timestamp_ms": now_ms + 1000,
            "properties": {"message": "NullPointerException"}
        }
    ]
    store.insert_events(events)

def test_collector_and_realtime_api():
    # 1. Post batch events
    resp = client.post("/api/v1/collect/events", json={
        "events": [
            {
                "event_name": "test_ping",
                "page_path": "/test",
                "event_type": "custom"
            }
        ]
    })
    assert resp.status_code == 200
    assert resp.json()["received_count"] == 1

    # 2. Get real-time stream
    rt_resp = client.get("/api/v1/collect/realtime?limit=10")
    assert rt_resp.status_code == 200
    assert len(rt_resp.json()["events"]) > 0

def test_funnel_operator():
    res = calculate_funnel(["view_item", "add_to_cart", "purchase_success"])
    assert res["initial_users"] == 2
    assert res["final_converted_users"] == 1
    assert res["overall_conversion_rate"] == 0.5
    assert len(res["steps"]) == 3

def test_flow_operator():
    res = calculate_user_flow()
    assert "nodes" in res
    assert "links" in res

def test_retention_and_page_metrics():
    ret = calculate_retention(days=3)
    assert "retention_matrix" in ret

    pages = calculate_page_metrics()
    assert "summary" in pages
    assert pages["summary"]["total_events"] > 0
    assert len(pages["pages"]) > 0

def test_trace_waterfall_and_replay():
    # Trace
    tr = get_trace_waterfall("trace_100")
    assert tr["total_spans"] >= 4

    # Replay
    rep = get_session_action_replay("sess_100")
    assert rep["action_count"] == 4

def test_dashboard_endpoint():
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "现代数据栈全链路智能分析与治理平台" in resp.text
