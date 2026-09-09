"""Dota 2 team & player analysis using the data-analysis-service, end to end.

Loads OpenDota-shaped match/player data into an analytical session, then uses the
service's SQL/OLAP, correlation, clustering and Insight Copilot operators to
profile teams and players (experience & habits) and derive rule-based tactical
guidance. Produces a Markdown report. Runs in-process (no server/auth).

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
from app.operators.sandbox import run_duckdb_sql
from app.operators.correlation import run_correlation_analysis
from app.operators.mining.clustering import run_kmeans_clustering
from app.copilot import discover_insights


def _load_session(data_dir: str, session_id: str = "dota2_demo"):
    sess = SessionManager().get_or_create_session(session_id)
    con = sess.get_duckdb_conn()
    for tbl in ("matches", "player_matches", "players", "teams"):
        path = os.path.join(data_dir, f"{tbl}.csv").replace("'", "''")
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    return sess.session_id, con


def _rows(sid, sql, limit=200):
    return run_duckdb_sql(sid, sql, limit=limit)["data"]


def run_dota2_analysis(data_dir: str, out_path: str) -> dict:
    if not os.path.exists(os.path.join(data_dir, "player_matches.csv")):
        import importlib.util
        gen_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_sample_data.py")
        spec = importlib.util.spec_from_file_location("dota2_generate_sample_data", gen_path)
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        gen.generate(data_dir)

    sid, con = _load_session(data_dir)

    team_stats = _rows(sid, """
        SELECT pm.team,
               count(DISTINCT pm.match_id) AS games,
               count(DISTINCT CASE WHEN pm.win=1 THEN pm.match_id END) AS wins,
               round(100.0*count(DISTINCT CASE WHEN pm.win=1 THEN pm.match_id END)
                     / count(DISTINCT pm.match_id), 1) AS winrate,
               round(avg(m.duration_min), 1) AS avg_duration_min
        FROM player_matches pm JOIN matches m ON pm.match_id = m.match_id
        GROUP BY pm.team ORDER BY winrate DESC
    """)

    player_stats = _rows(sid, """
        SELECT player_name, team, role, count(*) AS games,
               round(avg(kills),1) AS k, round(avg(deaths),1) AS d, round(avg(assists),1) AS a,
               round((avg(kills)+avg(assists))/greatest(avg(deaths),1),2) AS kda,
               round(avg(gpm)) AS gpm, round(avg(xpm)) AS xpm, round(avg(last_hits)) AS lh,
               count(DISTINCT hero) AS hero_pool_size,
               round(avg(win)*100,1) AS winrate
        FROM player_matches GROUP BY player_name, team, role
    """)

    hero_habits = _rows(sid, """
        SELECT team, hero, count(*) AS picks
        FROM player_matches GROUP BY team, hero ORDER BY team, picks DESC
    """)

    corr = run_correlation_analysis(sid, "player_matches",
                                    columns=["gpm", "xpm", "kills", "assists", "last_hits", "win"])
    clustering = run_kmeans_clustering(sid, "player_matches",
                                       feature_cols=["gpm", "xpm", "kills", "assists", "last_hits"])
    insights = discover_insights(sid, "player_matches", target_metric="gpm", category_col="role")

    overall_med = sorted(t["avg_duration_min"] for t in team_stats)[len(team_stats) // 2]
    guidance = _tactics(team_stats, player_stats, hero_habits, overall_med)

    report = _build_report(team_stats, player_stats, hero_habits, corr, clustering, insights, guidance, overall_med)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    return {"teams": len(team_stats), "players": len(player_stats),
            "report": out_path, "insights": insights["total_insights"]}


def _top_heroes(hero_habits, team, n=2):
    hs = [h for h in hero_habits if h["team"] == team]
    hs.sort(key=lambda x: x["picks"], reverse=True)
    return [h["hero"] for h in hs[:n]]


def _tactics(team_stats, player_stats, hero_habits, overall_med):
    g = []
    # Team-level: tempo vs scaling from win-durations
    for t in team_stats[:4]:
        tempo = t["avg_duration_min"] < overall_med
        sigs = _top_heroes(hero_habits, t["team"], 2)
        if tempo:
            plan = "早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。"
        else:
            plan = "后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。"
        g.append(f"**{t['team']}**（胜率 {t['winrate']}% · 均时长 {t['avg_duration_min']}min）：{plan} 优先 ban 其招牌英雄：{', '.join(sigs)}。")

    # Key threats: top GPM + top KDA
    by_gpm = sorted(player_stats, key=lambda p: p["gpm"], reverse=True)[:3]
    by_kda = sorted(player_stats, key=lambda p: p["kda"], reverse=True)[:3]
    threats = []
    for p in by_gpm:
        threats.append(f"{p['player_name']}({p['team']}/{p['role']}, GPM {p['gpm']})")
    g.append("**核心威胁（经济）**：优先针对 gank/切入 → " + "；".join(threats) + "。")
    g.append("**核心威胁（KDA）**：" + "；".join(f"{p['player_name']}(KDA {p['kda']})" for p in by_kda) + "。")

    # Predictable narrow-pool players
    narrow = [p for p in player_stats if p["hero_pool_size"] <= 2]
    if narrow:
        items = [f"{p['player_name']}（英雄池 {p['hero_pool_size']}）" for p in narrow[:5]]
        g.append("**可预测的窄英雄池选手**（针对性 ban/针对）：" + "；".join(items) + "。")
    return g


def _fmt(n):
    try:
        return f"{float(n):,.1f}" if isinstance(n, float) else f"{n}"
    except (TypeError, ValueError):
        return str(n)


def _table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_fmt(r.get(c)) for c in cols) + " |")
    return out


def _build_report(team_stats, player_stats, hero_habits, corr, clustering, insights, guidance, overall_med):
    L = ["# Dota 2 战队与选手分析报告\n",
         "> 由 data-analysis-service 端到端生成（SQL/OLAP · 相关性 · KMeans 打法聚类 · Insight Copilot）。数据结构对齐 OpenDota。\n"]

    L.append("## 1. 战队战绩总览")
    L += _table(team_stats, ["team", "games", "wins", "winrate", "avg_duration_min"])
    L.append(f"\n- 联赛平均对局时长中位数：**{overall_med} min**（作为节奏型/发育型分界）\n")

    L.append("## 2. 选手经验与数据（Top by GPM）")
    top_players = sorted(player_stats, key=lambda p: p["gpm"], reverse=True)[:12]
    L += _table(top_players, ["player_name", "team", "role", "games", "kda", "gpm", "xpm", "lh", "hero_pool_size", "winrate"])
    L.append("")

    L.append("## 3. 战队招牌英雄（习惯）")
    for t in team_stats[:6]:
        L.append(f"- **{t['team']}**：{', '.join(_top_heroes(hero_habits, t['team'], 3))}")
    L.append("")

    L.append("## 4. 关键相关性（表现 ↔ 胜负）")
    pairs = [p for p in corr.get("high_correlation_pairs", [])]
    if pairs:
        for p in pairs:
            L.append(f"- **{p['col1']} ↔ {p['col2']}**：r={p['r']}（{p['strength']}）")
    else:
        L.append("- 未发现强相关（样本噪声较高属正常）。")
    L.append("")

    L.append("## 5. 选手打法聚类 (KMeans)")
    L.append(f"- 自动最优簇数 k=**{clustering.get('optimal_k', clustering.get('n_clusters','?'))}**，"
             f"轮廓系数 {clustering.get('silhouette_score','N/A')}")
    for c in (clustering.get("clusters") or [])[:6]:
        size = c.get("size") or c.get("count")
        L.append(f"  - 簇 {c.get('cluster_id', c.get('cluster'))}: {size} 人")
    L.append("")

    L.append("## 6. 自动洞察 (Insight Copilot)")
    nar = insights.get("narrative", {})
    L.append(f"**{nar.get('headline','')}**\n")
    for s in nar.get("sections", []):
        L.append(f"- {s}")
    if nar.get("recommendation"):
        L.append(f"- **建议**：{nar['recommendation']}")
    L.append("")

    L.append("## 7. 战术指导 (Tactical Guidance)")
    for item in guidance:
        L.append(f"- {item}")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    res = run_dota2_analysis(os.path.join(here, "data"), os.path.join(here, "report.md"))
    print("Dota2 analysis done:", json.dumps(res, ensure_ascii=False))
