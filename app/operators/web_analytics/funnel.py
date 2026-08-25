from typing import List, Dict, Any, Optional
from app.storage.event_store import get_event_store

def calculate_funnel(
    steps: List[str],
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate multi-step sequential conversion funnel.
    """
    store = get_event_store()
    if not steps:
        return {"error": "Steps cannot be empty"}

    # Base query for users reaching each step in order
    step_results = []
    prev_users = None
    
    for idx, step_name in enumerate(steps):
        where_clauses = [f"event_name = '{step_name}'"]
        if date_from:
            where_clauses.append(f"created_at >= '{date_from}'")
        if date_to:
            where_clauses.append(f"created_at <= '{date_to}'")
        
        where_sql = " AND ".join(where_clauses)
        users_sql = f"SELECT DISTINCT user_id FROM events WHERE {where_sql}"
        
        if prev_users is None:
            sql = f"SELECT count(DISTINCT user_id) as count FROM events WHERE {where_sql}"
            res = store.query(sql)
            count = res[0]["count"] if res else 0
            prev_users = users_sql
        else:
            sql = f"SELECT count(DISTINCT user_id) as count FROM events WHERE {where_sql} AND user_id IN ({prev_users})"
            res = store.query(sql)
            count = res[0]["count"] if res else 0
            prev_users = f"{prev_users} INTERSECT {users_sql}"

        step_results.append({
            "step_index": idx + 1,
            "step_name": step_name,
            "user_count": int(count)
        })

    # Calculate conversion and drop-off rates
    first_count = step_results[0]["user_count"] if step_results else 0
    for idx, step in enumerate(step_results):
        if idx == 0:
            step["step_conversion_rate"] = 1.0
            step["overall_conversion_rate"] = 1.0 if first_count > 0 else 0.0
            step["drop_off_rate"] = 0.0
        else:
            prev_count = step_results[idx - 1]["user_count"]
            step["step_conversion_rate"] = round(step["user_count"] / prev_count, 4) if prev_count > 0 else 0.0
            step["overall_conversion_rate"] = round(step["user_count"] / first_count, 4) if first_count > 0 else 0.0
            step["drop_off_rate"] = round(1.0 - step["step_conversion_rate"], 4)

    return {
        "total_steps": len(steps),
        "initial_users": first_count,
        "final_converted_users": step_results[-1]["user_count"] if step_results else 0,
        "overall_conversion_rate": step_results[-1]["overall_conversion_rate"] if step_results else 0.0,
        "steps": step_results
    }
