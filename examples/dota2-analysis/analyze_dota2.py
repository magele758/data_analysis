"""Dota 2 team & player analysis (CLI) — thin wrapper over app.examples.dota2.

Loads OpenDota-shaped CSVs (sample or real) into a session and runs the shared
pipeline/report defined in app.examples.dota2, so the CLI and the web dashboard
produce identical analysis + tactical guidance.

Usage:
    python analyze_dota2.py
    run_dota2_analysis(data_dir, out_path)   # importable entry point (tests)
"""

import json
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app.cluster.session_manager import SessionManager
from app.examples.dota2 import analyze, data_note_from_meta, _read_meta


def run_dota2_analysis(data_dir: str, out_path: str, session_id: str = "dota2_demo") -> dict:
    if not os.path.exists(os.path.join(data_dir, "player_matches.csv")):
        import importlib.util
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_sample_data.py")
        spec = importlib.util.spec_from_file_location("dota2_generate_sample_data", gen_path)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        gen.generate(data_dir)

    sess = SessionManager().get_or_create_session(session_id)
    con = sess.get_duckdb_conn()
    for tbl in ("matches", "player_matches", "players", "teams"):
        raw = os.path.join(data_dir, f"{tbl}.csv")
        if not os.path.exists(raw):
            continue  # real OpenDota export omits players.csv; analyze needs only matches + player_matches
        path = raw.replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    note = data_note_from_meta(_read_meta(data_dir))
    res = analyze(sess.session_id, con, data_note=note)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(res["report_markdown"])
    return {"teams": res["teams"], "players": res["players"],
            "focus_team": res.get("focus_team"), "focus_games": res.get("focus_games"),
            "focus_winrate": res.get("focus_winrate"), "report": out_path}


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    # Prefer REAL OpenDota data (fetch via fetch_opendota.py); fall back to sample.
    real_dir = os.path.join(here, "real_data")
    data_dir = real_dir if os.path.exists(os.path.join(real_dir, "player_matches.csv")) else os.path.join(here, "data")
    if data_dir != real_dir:
        print("[note] real_data not found — using sample. Run 'python fetch_opendota.py' for real OpenDota data.")
    print("Dota2 analysis done:", json.dumps(
        run_dota2_analysis(data_dir, os.path.join(here, "report.md")),
        ensure_ascii=False))
