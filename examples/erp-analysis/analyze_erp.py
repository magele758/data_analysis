"""ERP enterprise data analysis (CLI) — thin wrapper over app.examples.erp.

Loads the ERP CSVs (sample or real Kaggle data) into an analytical session and
runs the shared pipeline/report defined in app.examples.erp, so the CLI and the
web dashboard produce identical analysis. Writes a Markdown report.

Usage:
    python analyze_erp.py                 # auto-generates sample CSVs, writes report.md
    run_erp_analysis(data_dir, out_path)  # importable entry point (tests)
"""

import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.cluster.session_manager import SessionManager
from app.examples.erp import TABLES, build_fact, analyze


def _load_generator():
    import importlib.util
    gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_sample_data.py")
    spec = importlib.util.spec_from_file_location("erp_generate_sample_data", gen_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_erp_analysis(data_dir: str, out_path: str, session_id: str = "erp_demo") -> dict:
    if not os.path.exists(os.path.join(data_dir, "sales_order_lines.csv")):
        _load_generator().generate(data_dir)

    sess = SessionManager().get_or_create_session(session_id)
    con = sess.get_duckdb_conn()
    for tbl in TABLES:
        path = os.path.join(data_dir, f"{tbl}.csv").replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    build_fact(con)
    res = analyze(sess.session_id, con)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(res["report_markdown"])
    return {"rows": res["rows"], "report": out_path, "insights": res["insights"]["total_insights"]}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    print("ERP analysis done:", json.dumps(
        run_erp_analysis(os.path.join(here, "data"), os.path.join(here, "report.md")),
        ensure_ascii=False))
