import math
from typing import Dict, Any, List
from app.storage.event_store import get_event_store

def calculate_page_metrics(limit: int = 20) -> Dict[str, Any]:
    """
    Calculate Pageview (PV), Unique Visitors (UV), and Dwell Time by Page Path.
    """
    store = get_event_store()

    sql = """
    SELECT 
        page_path,
        count(*) as pv,
        count(DISTINCT user_id) as uv,
        count(DISTINCT session_id) as sessions,
        avg(CASE WHEN event_name = '$page_leave' THEN CAST(json_extract(properties, '$.dwell_time_seconds') AS DOUBLE) ELSE NULL END) as avg_dwell_time_sec
    FROM events
    WHERE page_path IS NOT NULL
    GROUP BY page_path
    ORDER BY pv DESC
    LIMIT ?
    """

    rows = store.query(sql, [limit])
    pages = []
    for r in rows:
        # avg() 在该分组无有效 dwell 值时可能产出 NaN/Inf，而两者都不是 None，
        # 会穿过判空直接进 json.dumps 并抛 ValueError（整个端点 500）。
        # isfinite 一次覆盖 NaN 与 ±Inf。
        dwell = r.get("avg_dwell_time_sec")
        dwell_val = float(dwell) if dwell is not None else 0.0
        if not math.isfinite(dwell_val):
            dwell_val = 0.0
        pages.append({
            "page_path": r["page_path"],
            "pv": int(r["pv"]),
            "uv": int(r["uv"]),
            "sessions": int(r["sessions"]),
            "avg_dwell_seconds": round(dwell_val, 1)
        })

    # Summary metrics
    summary_sql = """
    SELECT 
        count(*) as total_events,
        count(DISTINCT user_id) as total_uv,
        count(DISTINCT session_id) as total_sessions,
        count(CASE WHEN event_type = 'error' THEN 1 END) as total_errors
    FROM events
    """
    summary = store.query(summary_sql)
    sum_data = summary[0] if summary else {}

    return {
        "summary": {
            "total_events": int(sum_data.get("total_events", 0)),
            "total_uv": int(sum_data.get("total_uv", 0)),
            "total_sessions": int(sum_data.get("total_sessions", 0)),
            "total_errors": int(sum_data.get("total_errors", 0))
        },
        "pages": pages
    }
