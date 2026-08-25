from typing import Dict, Any, List, Optional
import numpy as np
import scipy.stats as stats
from app.cluster.session_manager import SessionManager

def detect_trends(
    session_id: str,
    dataset_name: str,
    time_col: str,
    metric: str,
    group_col: Optional[str] = None
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    group_clause = f', "{group_col}"' if group_col else ""
    sql = f"""
    SELECT "{time_col}"{group_clause}, SUM("{metric}") AS val
    FROM {dataset_name}
    WHERE "{metric}" IS NOT NULL
    GROUP BY "{time_col}"{group_clause}
    ORDER BY "{time_col}" ASC
    """
    df = con.execute(sql).df()
    
    x = np.arange(len(df))
    y = df["val"].values

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    r_squared = r_value ** 2

    change_points = []
    if len(y) >= 6:
        half = len(y) // 2
        s1, _, _, _, _ = stats.linregress(np.arange(half), y[:half])
        s2, _, _, _, _ = stats.linregress(np.arange(len(y) - half), y[half:])
        if np.sign(s1) != np.sign(s2) and abs(s1 - s2) > 0.1:
            change_points.append({
                "index": half,
                "time_point": str(df[time_col].iloc[half]),
                "trend_before": "Upward" if s1 > 0 else "Downward",
                "trend_after": "Upward" if s2 > 0 else "Downward"
            })

    direction = "Upward (Increasing)" if slope > 0 else ("Downward (Decreasing)" if slope < 0 else "Flat")
    significant = bool(p_value < 0.05)

    return {
        "time_col": time_col,
        "metric": metric,
        "trend_direction": direction,
        "slope": round(float(slope), 4),
        "r_squared": round(float(r_squared), 4),
        "p_value": round(float(p_value), 6),
        "statistically_significant": significant,
        "change_points": change_points,
        "series_preview": [{"time": str(r[time_col]), "val": round(float(r["val"]), 2)} for _, r in df.head(20).iterrows()]
    }
