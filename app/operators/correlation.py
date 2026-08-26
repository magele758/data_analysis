from typing import List, Dict, Any, Optional
import duckdb
import numpy as np
import scipy.stats as stats
from app.cluster.session_manager import SessionManager
from app.engine.sql_guard import safe_columns, safe_table_ref

def run_correlation_analysis(
    session_id: str,
    dataset_name: str,
    columns: Optional[List[str]] = None,
    method: str = "pearson"
) -> Dict[str, Any]:
    mgr = SessionManager()
    sess = mgr.get_session(session_id)
    if not sess:
        raise ValueError(f"Session '{session_id}' not found")
    con = sess.get_duckdb_conn()

    table_ref = safe_table_ref(dataset_name)

    if not columns:
        desc = con.execute(f"DESCRIBE {table_ref}").fetchall()
        columns = [
            r[0] for r in desc
            if any(num_t in str(r[1]).lower() for num_t in ["int", "float", "double", "decimal"])
        ]

    if len(columns) < 2:
        raise ValueError("At least 2 numeric columns required for correlation analysis")

    cols_sql = safe_columns(columns)
    data_table = con.execute(f"SELECT {cols_sql} FROM {table_ref}").df().dropna()
    
    n_cols = len(columns)
    corr_matrix = []
    high_correlation_pairs = []

    for i in range(n_cols):
        row = []
        for j in range(n_cols):
            c1, c2 = columns[i], columns[j]
            if i == j:
                r_val, p_val = 1.0, 0.0
            else:
                if method.lower() == "spearman":
                    r_val, p_val = stats.spearmanr(data_table[c1], data_table[c2])
                else:
                    r_val, p_val = stats.pearsonr(data_table[c1], data_table[c2])
            
            row.append({"r": round(float(r_val), 4), "p_value": round(float(p_val), 6)})
            
            if i < j and abs(r_val) >= 0.7:
                high_correlation_pairs.append({
                    "col1": c1,
                    "col2": c2,
                    "r": round(float(r_val), 4),
                    "p_value": round(float(p_val), 6),
                    "strength": "Very Strong" if abs(r_val) >= 0.85 else "Strong"
                })
        corr_matrix.append(row)

    return {
        "columns": columns,
        "method": method,
        "matrix": corr_matrix,
        "high_correlation_pairs": high_correlation_pairs,
        "sample_size": len(data_table)
    }
