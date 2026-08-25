from typing import Dict, Any, Optional
from app.storage.event_store import get_event_store

def calculate_user_flow(limit_paths: int = 15) -> Dict[str, Any]:
    """
    Calculate page transition matrix and Sankey flow nodes/links.
    """
    store = get_event_store()

    # Query contiguous page transition pairs (N-gram) partitioned by session_id ordered by timestamp
    sql = """
    WITH ordered_pages AS (
        SELECT 
            session_id,
            page_path AS source_page,
            LEAD(page_path) OVER (PARTITION BY session_id ORDER BY timestamp_ms ASC) AS target_page
        FROM events
        WHERE event_type = 'pageview' AND event_name = '$pageview'
    )
    SELECT 
        source_page,
        target_page,
        count(*) AS flow_volume
    FROM ordered_pages
    WHERE target_page IS NOT NULL AND source_page != target_page
    GROUP BY source_page, target_page
    ORDER BY flow_volume DESC
    LIMIT ?
    """
    
    raw_flows = store.query(sql, [limit_paths])
    
    nodes_set = set()
    links = []
    for row in raw_flows:
        src = str(row["source_page"])
        tgt = str(row["target_page"])
        val = int(row["flow_volume"])
        nodes_set.add(src)
        nodes_set.add(tgt)
        links.append({
            "source": src,
            "target": tgt,
            "value": val
        })

    nodes = [{"name": n} for n in sorted(list(nodes_set))]

    return {
        "nodes": nodes,
        "links": links,
        "total_transitions": sum(l["value"] for l in links)
    }
