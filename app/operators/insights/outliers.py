from typing import Dict, Any, List, Optional
import numpy as np
from sklearn.ensemble import IsolationForest
from app.cluster.session_manager import SessionManager

def detect_outliers(
    session_id: str,
    dataset_name: str,
    metric: str,
    dimension_cols: Optional[List[str]] = None,
    method: str = "z_score",
    threshold: float = 3.0,
    top_k: int = 10
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    dim_clause = ", ".join([f'"{d}"' for d in dimension_cols]) if dimension_cols else ""
    select_clause = ", ".join(filter(None, [dim_clause, f'"{metric}"']))
    df = con.execute(f'SELECT {select_clause} FROM {dataset_name} WHERE "{metric}" IS NOT NULL').df()

    vals = df[metric].values
    mean_v = float(np.mean(vals))
    std_v = float(np.std(vals))
    outlier_rows = []

    if method.lower() == "z_score":
        z_scores = (vals - mean_v) / (std_v if std_v > 0 else 1.0)
        df["_z_score"] = z_scores
        outliers_df = df[np.abs(df["_z_score"]) >= threshold].copy()
        outliers_df["_abs_z"] = np.abs(outliers_df["_z_score"])
        outliers_df = outliers_df.sort_values(by="_abs_z", ascending=False).head(top_k)

        for _, r in outliers_df.iterrows():
            item = {"value": float(r[metric]), "z_score": round(float(r["_z_score"]), 2), "deviation_from_mean": round(float(r[metric] - mean_v), 2)}
            if dimension_cols:
                item["dimensions"] = {d: str(r[d]) for d in dimension_cols}
            outlier_rows.append(item)

    elif method.lower() == "iqr":
        q25, q75 = np.percentile(vals, 25), np.percentile(vals, 75)
        iqr = q75 - q25
        lower_bound = q25 - 1.5 * iqr
        upper_bound = q75 + 1.5 * iqr
        outliers_df = df[(df[metric] < lower_bound) | (df[metric] > upper_bound)].head(top_k)
        for _, r in outliers_df.iterrows():
            item = {"value": float(r[metric]), "lower_bound": round(lower_bound, 2), "upper_bound": round(upper_bound, 2)}
            if dimension_cols:
                item["dimensions"] = {d: str(r[d]) for d in dimension_cols}
            outlier_rows.append(item)

    elif method.lower() == "isolation_forest":
        iso = IsolationForest(contamination=0.01, random_state=42)
        preds = iso.fit_predict(vals.reshape(-1, 1))
        df["_is_outlier"] = (preds == -1)
        outliers_df = df[df["_is_outlier"]].head(top_k)
        for _, r in outliers_df.iterrows():
            item = {"value": float(r[metric]), "anomaly_score": "High"}
            if dimension_cols:
                item["dimensions"] = {d: str(r[d]) for d in dimension_cols}
            outlier_rows.append(item)

    return {
        "metric": metric,
        "method": method,
        "baseline_mean": round(mean_v, 2),
        "baseline_std": round(std_v, 2),
        "outlier_count": len(outlier_rows),
        "outliers": outlier_rows
    }
