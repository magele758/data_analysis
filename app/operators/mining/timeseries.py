from typing import Dict, Any, List, Optional
import numpy as np
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA
from app.cluster.session_manager import SessionManager
from app.engine.sql_guard import safe_ident, safe_table_ref

def run_timeseries_forecast(
    session_id: str,
    dataset_name: str,
    time_col: str,
    value_col: str,
    horizon: int = 12,
    model_type: str = "arima"
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    val_ref = safe_ident(value_col)
    sql = f"""
    SELECT {safe_ident(time_col)}, SUM({val_ref}) AS val
    FROM {safe_table_ref(dataset_name)}
    WHERE {val_ref} IS NOT NULL
    GROUP BY 1
    ORDER BY 1 ASC
    """
    df = con.execute(sql).df()
    vals = df["val"].values

    if len(vals) < 10:
        raise ValueError("At least 10 historical time-points required for forecasting")

    forecast_items = []
    if model_type.lower() == "arima":
        model = ARIMA(vals, order=(1, 1, 1)).fit()
        forecast_res = model.get_forecast(steps=horizon)
        predicted_mean = forecast_res.predicted_mean
        conf_int = forecast_res.conf_int(alpha=0.05)

        for h in range(horizon):
            forecast_items.append({
                "step": h + 1,
                "predicted_value": round(float(predicted_mean[h]), 2),
                "ci_95_lower": round(float(conf_int[h, 0]), 2),
                "ci_95_upper": round(float(conf_int[h, 1]), 2)
            })
    else:
        model = ExponentialSmoothing(vals, trend="add").fit()
        preds = model.forecast(horizon)
        std_err = np.std(model.resid)
        for h in range(horizon):
            forecast_items.append({
                "step": h + 1,
                "predicted_value": round(float(preds[h]), 2),
                "ci_95_lower": round(float(preds[h] - 1.96 * std_err), 2),
                "ci_95_upper": round(float(preds[h] + 1.96 * std_err), 2)
            })

    return {
        "time_col": time_col,
        "value_col": value_col,
        "model": model_type,
        "horizon_steps": horizon,
        "forecasts": forecast_items,
        "historical_preview": [{"time": str(df[time_col].iloc[i]), "value": round(float(vals[i]), 2)} for i in range(min(15, len(vals)))]
    }
