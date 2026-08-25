from typing import Dict, Any, List
import pandas as pd
from app.storage.event_store import get_event_store

def calculate_retention(days: int = 7) -> Dict[str, Any]:
    """
    Calculate Cohort retention heatmap matrix.
    """
    store = get_event_store()

    sql = """
    WITH first_active AS (
        SELECT 
            user_id,
            min(strftime(created_at, '%Y-%m-%d')) AS cohort_date,
            min(created_at) AS first_time
        FROM events
        GROUP BY user_id
    ),
    activity AS (
        SELECT DISTINCT
            e.user_id,
            f.cohort_date,
            datediff('day', f.first_time, e.created_at) AS day_diff
        FROM events e
        JOIN first_active f ON e.user_id = f.user_id
        WHERE datediff('day', f.first_time, e.created_at) BETWEEN 0 AND ?
    )
    SELECT 
        cohort_date,
        day_diff,
        count(DISTINCT user_id) as active_users
    FROM activity
    GROUP BY cohort_date, day_diff
    ORDER BY cohort_date ASC, day_diff ASC
    """

    rows = store.query(sql, [days])
    if not rows:
        return {"cohorts": [], "retention_matrix": []}

    df = pd.DataFrame(rows)
    cohort_sizes = df[df["day_diff"] == 0].set_index("cohort_date")["active_users"].to_dict()

    matrix = []
    for c_date, group in df.groupby("cohort_date"):
        c_size = cohort_sizes.get(c_date, 1)
        row_dict = {
            "cohort_date": str(c_date),
            "cohort_size": int(c_size)
        }
        for d in range(days + 1):
            day_match = group[group["day_diff"] == d]
            if not day_match.empty:
                cnt = int(day_match.iloc[0]["active_users"])
                rate = round(cnt / c_size, 4) if c_size > 0 else 0.0
                row_dict[f"day_{d}"] = {"count": cnt, "rate": rate}
            else:
                row_dict[f"day_{d}"] = {"count": 0, "rate": 0.0}
        matrix.append(row_dict)

    return {
        "cohorts": list(cohort_sizes.keys()),
        "days_analyzed": days,
        "retention_matrix": matrix
    }
