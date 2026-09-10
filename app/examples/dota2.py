"""Built-in Dota 2 example: in-memory sample + analysis + tactical guidance.

Single source of truth for the Dota2 demo (web endpoint + CLI). Generates an
OpenDota-shaped season, lands it in a session, and drives SQL/OLAP + correlation
+ KMeans clustering + Insight Copilot, then derives rule-based tactical guidance.
"""

import os
import random
from typing import Any, Dict, List

import pandas as pd

from app.cluster.session_manager import SessionManager
from app.operators.sandbox import run_duckdb_sql
from app.operators.correlation import run_correlation_analysis
from app.operators.mining.clustering import run_kmeans_clustering
from app.copilot import discover_insights

EXAMPLE_ID = "dota2"
NAME = "Dota2 战队与选手分析"
DOMAIN = "Esports · Dota 2 (OpenDota, 真实数据)"
DESCRIPTION = "真实 OpenDota 数据（Xtreme Gaming）· 战队战绩 · 选手习惯 · KMeans 聚类 · Insight Copilot · 战术指导"

# Real data fetched from the OpenDota API (see examples/dota2-analysis/fetch_opendota.py),
# bundled in the repo. run_in_memory loads this by default; the synthetic generator
# below is only an offline fallback if the real CSVs are absent.
REAL_DATA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "examples", "dota2-analysis", "real_data"))

# Xtreme Gaming (XG) is a real top-tier team; included as the strongest sample
# team so it stands out in the report. See README for pulling real XG data from
# the OpenDota /teams/{team_id} endpoints.
_TEAMS = [("Xtreme Gaming", 0.75), ("Team Alpha", 0.72), ("Team Bravo", 0.66), ("Team Cobra", 0.58),
          ("Team Delta", 0.52), ("Team Echo", 0.47), ("Team Falcon", 0.42), ("Team Ghost", 0.36),
          ("Team Hydra", 0.30)]
_ROLES = ["Carry", "Mid", "Offlane", "Support", "HardSupport"]
_HEROES = {
    "Carry": ["Faceless Void", "Juggernaut", "Phantom Assassin", "Terrorblade", "Spectre", "Medusa"],
    "Mid": ["Invoker", "Storm Spirit", "Puck", "Queen of Pain", "Ember Spirit", "Lina"],
    "Offlane": ["Mars", "Tidehunter", "Centaur", "Underlord", "Axe", "Beastmaster"],
    "Support": ["Crystal Maiden", "Rubick", "Jakiro", "Lion", "Shadow Shaman"],
    "HardSupport": ["Dazzle", "Warlock", "Treant Protector", "Witch Doctor", "Io"],
}


def generate_frames(seed: int = 7, n_matches: int = 160) -> Dict[str, pd.DataFrame]:
    from datetime import date, timedelta
    rng = random.Random(seed)
    teams, players, meta = [], [], {}
    for tid, (tname, skill) in enumerate(_TEAMS, start=1):
        style = "tempo" if tid % 2 == 1 else "scaling"
        teams.append({"team_id": tid, "name": tname, "skill": skill, "style": style})
        meta[tname] = {"skill": skill, "style": style, "players": []}
        for r_idx, role in enumerate(_ROLES):
            pool_size = 2 if (tid + r_idx) % 4 == 0 else rng.randint(3, 4)
            pool = rng.sample(_HEROES[role], pool_size)
            p = {"account_id": tid * 100 + r_idx, "player_name": f"{tname.split()[1][:3]}_{role[:3]}",
                 "team": tname, "role": role, "hero_pool": "|".join(pool),
                 "skill": round(min(0.95, skill + rng.uniform(-0.05, 0.08)), 3)}
            players.append(p)
            meta[tname]["players"].append(p)

    start = date(2025, 1, 1)
    names = [t["name"] for t in teams]
    matches, pms = [], []
    for mid in range(1, n_matches + 1):
        a, b = rng.sample(names, 2)
        sa, sb = meta[a]["skill"], meta[b]["skill"]
        winner = a if rng.random() < sa / (sa + sb) else b
        base = 28 if meta[winner]["style"] == "tempo" else 44
        duration = max(18, round(rng.gauss(base, 6), 1))
        mdate = (start + timedelta(days=rng.randint(0, 250))).isoformat()
        matches.append({"match_id": 7_000_000_000 + mid, "start_date": mdate, "duration_min": duration,
                        "radiant_team": a, "dire_team": b, "winner": winner, "league": "Sample Pro League S1"})
        for tname in (a, b):
            won = tname == winner
            for p in meta[tname]["players"]:
                s = _stats(rng, p["role"], p["skill"], won)
                pms.append({"match_id": 7_000_000_000 + mid, "start_date": mdate,
                            "account_id": p["account_id"], "player_name": p["player_name"],
                            "team": tname, "role": p["role"], "hero": rng.choice(p["hero_pool"].split("|")),
                            "kills": s["k"], "deaths": s["d"], "assists": s["a"],
                            "gpm": s["gpm"], "xpm": s["xpm"], "last_hits": s["lh"],
                            "win": 1 if won else 0})
    return {"matches": pd.DataFrame(matches), "player_matches": pd.DataFrame(pms),
            "players": pd.DataFrame(players),
            "teams": pd.DataFrame([{k: t[k] for k in ("team_id", "name", "skill", "style")} for t in teams])}


def _stats(rng, role, skill, won):
    wb = 1.15 if won else 0.9
    table = {
        "Carry": (620, 280, 9, 5, 9), "Mid": (580, 230, 10, 6, 11), "Offlane": (450, 150, 6, 7, 15),
        "Support": (320, 60, 4, 8, 18), "HardSupport": (280, 40, 3, 9, 20),
    }
    g, lh, k, d, a = table[role]
    gpm = max(150, round(rng.gauss(g * skill * wb, 55)))
    return {"gpm": gpm, "xpm": max(150, round(gpm * rng.uniform(0.9, 1.1))),
            "lh": max(10, round(rng.gauss(lh * (wb if role in ("Carry", "Mid", "Offlane") else 1), 30))),
            "k": max(0, round(rng.gauss(k, 3))), "d": max(1, round(rng.gauss(d, 2))),
            "a": max(0, round(rng.gauss(a, 4)))}


def register_frames(con, frames):
    for name in ("matches", "player_matches", "players", "teams"):
        con.register(f"_src_{name}", frames[name])
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _src_{name}")
        con.unregister(f"_src_{name}")


def analyze(session_id: str, con, data_note: str = None) -> Dict[str, Any]:
    def rows(sql):
        return run_duckdb_sql(session_id, sql, limit=200)["data"]

    team_stats = rows("""
        SELECT pm.team, count(DISTINCT pm.match_id) AS games,
               count(DISTINCT CASE WHEN pm.win=1 THEN pm.match_id END) AS wins,
               round(100.0*count(DISTINCT CASE WHEN pm.win=1 THEN pm.match_id END)/count(DISTINCT pm.match_id),1) AS winrate,
               round(avg(m.duration_min),1) AS avg_duration_min
        FROM player_matches pm JOIN matches m ON pm.match_id=m.match_id
        GROUP BY pm.team ORDER BY winrate DESC""")
    player_stats = rows("""
        SELECT player_name, team, role, count(*) AS games,
               round((avg(kills)+avg(assists))/greatest(avg(deaths),1),2) AS kda,
               round(avg(gpm)) AS gpm, round(avg(xpm)) AS xpm, round(avg(last_hits)) AS lh,
               count(DISTINCT hero) AS hero_pool_size, round(avg(win)*100,1) AS winrate
        FROM player_matches GROUP BY player_name, team, role""")
    hero_habits = rows("SELECT team, hero, count(*) AS picks FROM player_matches GROUP BY team, hero ORDER BY team, picks DESC")

    corr = run_correlation_analysis(session_id, "player_matches",
                                    columns=["gpm", "xpm", "kills", "assists", "last_hits", "win"])
    clustering = run_kmeans_clustering(session_id, "player_matches",
                                       feature_cols=["gpm", "xpm", "kills", "assists", "last_hits"])
    insights = discover_insights(session_id, "player_matches", target_metric="gpm", category_col="role")

    med = sorted(t["avg_duration_min"] for t in team_stats)[len(team_stats) // 2]
    guidance = _tactics(team_stats, player_stats, hero_habits, med)
    report = _report(team_stats, player_stats, hero_habits, corr, clustering, insights, guidance, med, data_note)
    return {"example_id": EXAMPLE_ID, "name": NAME, "domain": DOMAIN,
            "session_id": session_id, "dataset_name": "player_matches",
            "teams": len(team_stats), "players": len(player_stats),
            "data_note": data_note, "insights": insights, "report_markdown": report}


def _read_meta(data_dir: str):
    import json
    path = os.path.join(data_dir, "_meta.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def data_note_from_meta(meta) -> str:
    if meta:
        return (f"数据来源：{meta.get('source', 'OpenDota API')} · 战队：{meta.get('team', 'Xtreme Gaming')}"
                f"（team_id={meta.get('team_id')}）· **数据获取日期：{meta.get('fetched_at', '未知')}**")
    return "数据来源：合成样本（离线后备，非真实数据）"


def _load_real_tables(con) -> bool:
    """Load the bundled real OpenDota CSVs into the session. Returns False if absent."""
    if not os.path.exists(os.path.join(REAL_DATA_DIR, "player_matches.csv")):
        return False
    for tbl in ("matches", "player_matches", "teams"):
        path = os.path.join(REAL_DATA_DIR, f"{tbl}.csv")
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path)
        con.register(f"_src_{tbl}", df)
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM _src_{tbl}")
        con.unregister(f"_src_{tbl}")
    return True


def run_in_memory(session_id: str = None, seed: int = 7) -> Dict[str, Any]:
    sess = SessionManager().get_or_create_session(session_id)
    con = sess.get_duckdb_conn()
    if _load_real_tables(con):
        note = data_note_from_meta(_read_meta(REAL_DATA_DIR))
    else:  # offline fallback only
        register_frames(con, generate_frames(seed))
        note = data_note_from_meta(None)
    return analyze(sess.session_id, con, data_note=note)


def _top_heroes(hero_habits, team, n=2):
    hs = sorted([h for h in hero_habits if h["team"] == team], key=lambda x: x["picks"], reverse=True)
    return [h["hero"] for h in hs[:n]]


def _tactics(team_stats, player_stats, hero_habits, med) -> List[str]:
    g = []
    for t in team_stats[:4]:
        tempo = t["avg_duration_min"] < med
        plan = ("早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。" if tempo
                else "后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。")
        g.append(f"**{t['team']}**（胜率 {t['winrate']}% · 均时长 {t['avg_duration_min']}min）：{plan} 优先 ban 招牌英雄：{', '.join(_top_heroes(hero_habits, t['team'], 2))}。")
    by_gpm = sorted(player_stats, key=lambda p: p["gpm"], reverse=True)[:3]
    by_kda = sorted(player_stats, key=lambda p: p["kda"], reverse=True)[:3]
    g.append("**核心威胁（经济）**：优先 gank/切入 → " + "；".join(f"{p['player_name']}({p['team']}/{p['role']}, GPM {p['gpm']})" for p in by_gpm) + "。")
    g.append("**核心威胁（KDA）**：" + "；".join(f"{p['player_name']}(KDA {p['kda']})" for p in by_kda) + "。")
    narrow = [p for p in player_stats if p["hero_pool_size"] <= 2]
    if narrow:
        g.append("**可预测的窄英雄池选手**（针对性 ban）：" + "；".join(f"{p['player_name']}（池 {p['hero_pool_size']}）" for p in narrow[:5]) + "。")
    return g


def _f(n):
    try:
        return f"{float(n):,.1f}" if isinstance(n, float) else f"{n}"
    except (TypeError, ValueError):
        return str(n)


def _table(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_f(r.get(c)) for c in cols) + " |")
    return out


def _report(team_stats, player_stats, hero_habits, corr, clustering, insights, guidance, med, data_note=None) -> str:
    L = ["# Dota 2 战队与选手分析报告\n",
         "> 由 data-analysis-service 端到端生成（SQL/OLAP · 相关性 · KMeans 打法聚类 · Insight Copilot）。数据结构对齐 OpenDota。"]
    if data_note:
        L.append(f"> {data_note}")
    L.append("")
    L.append("## 1. 战队战绩总览")
    L += _table(team_stats, ["team", "games", "wins", "winrate", "avg_duration_min"])
    L.append(f"\n- 联赛对局时长中位数：**{med} min**（节奏型/发育型分界）\n")
    L.append("## 2. 选手经验与数据（Top by GPM）")
    L += _table(sorted(player_stats, key=lambda p: p["gpm"], reverse=True)[:12],
                ["player_name", "team", "role", "games", "kda", "gpm", "xpm", "lh", "hero_pool_size", "winrate"])
    L.append("")
    L.append("## 3. 战队招牌英雄（习惯）")
    for t in team_stats[:6]:
        L.append(f"- **{t['team']}**：{', '.join(_top_heroes(hero_habits, t['team'], 3))}")
    L.append("")
    L.append("## 4. 关键相关性（表现 ↔ 胜负）")
    for p in corr.get("high_correlation_pairs", []) or [{"col1": "-", "col2": "-", "r": "-", "strength": "无强相关"}]:
        L.append(f"- **{p['col1']} ↔ {p['col2']}**：r={p['r']}（{p['strength']}）")
    L.append("")
    L.append("## 5. 选手打法聚类 (KMeans)")
    L.append(f"- 自动最优簇数 k=**{clustering.get('optimal_k', clustering.get('n_clusters','?'))}**，轮廓系数 {clustering.get('silhouette_score','N/A')}")
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
