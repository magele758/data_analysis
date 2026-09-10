"""Generate a small, seeded Dota 2 sample dataset (pro-scene shaped).

Schema mirrors OpenDota's public data (api.opendota.com) so real data can be
dropped in with minimal remapping:
  - matches.csv        ~ /proMatches  (match_id, start_date, duration, teams, winner, league)
  - player_matches.csv ~ /matches[].players + /teams/{id}/players
                         (match_id, account_id, player_name, team, hero, role,
                          kills, deaths, assists, gpm, xpm, last_hits, win)
  - teams.csv          ~ /teams

See README for the OpenDota endpoint -> column mapping.
"""

import csv
import os
import random
from datetime import date, timedelta

TEAMS = [
    ("Xtreme Gaming", 0.75),  # real top-tier team (XG); strongest sample team
    ("Team Alpha", 0.72), ("Team Bravo", 0.66), ("Team Cobra", 0.58),
    ("Team Delta", 0.52), ("Team Echo", 0.47), ("Team Falcon", 0.42),
    ("Team Ghost", 0.36), ("Team Hydra", 0.30),
]
ROLES = ["Carry", "Mid", "Offlane", "Support", "HardSupport"]
HERO_POOL = {
    "Carry": ["Faceless Void", "Juggernaut", "Phantom Assassin", "Terrorblade", "Spectre", "Medusa"],
    "Mid": ["Invoker", "Storm Spirit", "Puck", "Queen of Pain", "Ember Spirit", "Lina"],
    "Offlane": ["Mars", "Tidehunter", "Centaur", "Underlord", "Axe", "Beastmaster"],
    "Support": ["Crystal Maiden", "Rubick", "Jakiro", "Lion", "Shadow Shaman"],
    "HardSupport": ["Dazzle", "Warlock", "Treant Protector", "Witch Doctor", "Io"],
}


def generate(out_dir: str, seed: int = 7):
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)

    teams, players = [], []
    team_meta = {}
    for tid, (tname, skill) in enumerate(TEAMS, start=1):
        # "tempo" teams win fast; "scaling" teams win long — a signal for tactics.
        style = "tempo" if tid % 2 == 1 else "scaling"
        teams.append({"team_id": tid, "name": tname, "skill": skill, "style": style})
        team_meta[tname] = {"skill": skill, "style": style}
        for r_idx, role in enumerate(ROLES):
            # Some players have a narrow hero pool (predictable habit) -> tactics.
            pool_size = 2 if (tid + r_idx) % 4 == 0 else rng.randint(3, 4)
            pool = rng.sample(HERO_POOL[role], pool_size)
            players.append({
                "account_id": tid * 100 + r_idx,
                "player_name": f"{tname.split()[1][:3]}_{role[:3]}",
                "team": tname,
                "role": role,
                "hero_pool": "|".join(pool),
                "skill": round(min(0.95, skill + rng.uniform(-0.05, 0.08)), 3),
            })
    _write(out_dir, "teams.csv", [{k: t[k] for k in ("team_id", "name", "skill", "style")} for t in teams])

    players_by_team = {}
    for p in players:
        players_by_team.setdefault(p["team"], []).append(p)

    start = date(2025, 1, 1)
    matches, player_matches = [], []
    names = [t["name"] for t in teams]
    for mid in range(1, 161):
        a, b = rng.sample(names, 2)
        sa, sb = team_meta[a]["skill"], team_meta[b]["skill"]
        p_a_win = sa / (sa + sb)
        a_win = rng.random() < p_a_win
        winner = a if a_win else b
        # tempo team winning -> shorter game; scaling -> longer
        wstyle = team_meta[winner]["style"]
        base = 28 if wstyle == "tempo" else 44
        duration_min = max(18, round(rng.gauss(base, 6), 1))
        mdate = start + timedelta(days=rng.randint(0, 250))
        matches.append({
            "match_id": 7000000000 + mid,
            "start_date": mdate.isoformat(),
            "duration_min": duration_min,
            "radiant_team": a, "dire_team": b,
            "winner": winner,
            "league": "Sample Pro League S1",
        })
        for team_name in (a, b):
            team_won = (team_name == winner)
            for p in players_by_team[team_name]:
                hero = rng.choice(p["hero_pool"].split("|"))
                stats = _stats(rng, p["role"], p["skill"], team_won)
                player_matches.append({
                    "match_id": 7000000000 + mid,
                    "start_date": mdate.isoformat(),
                    "account_id": p["account_id"],
                    "player_name": p["player_name"],
                    "team": team_name,
                    "role": p["role"],
                    "hero": hero,
                    "kills": stats["k"], "deaths": stats["d"], "assists": stats["a"],
                    "gpm": stats["gpm"], "xpm": stats["xpm"], "last_hits": stats["lh"],
                    "win": 1 if team_won else 0,
                })

    _write(out_dir, "matches.csv", matches)
    _write(out_dir, "player_matches.csv", player_matches)
    _write(out_dir, "players.csv", players)
    return {"teams": len(teams), "players": len(players),
            "matches": len(matches), "player_matches": len(player_matches)}


def _stats(rng, role, skill, won):
    win_bonus = 1.15 if won else 0.9
    if role == "Carry":
        gpm = rng.gauss(620 * skill * win_bonus, 60); lh = rng.gauss(280 * win_bonus, 40)
        k, d, a = rng.gauss(9, 3), rng.gauss(5, 2), rng.gauss(9, 3)
    elif role == "Mid":
        gpm = rng.gauss(580 * skill * win_bonus, 60); lh = rng.gauss(230 * win_bonus, 40)
        k, d, a = rng.gauss(10, 3), rng.gauss(6, 2), rng.gauss(11, 3)
    elif role == "Offlane":
        gpm = rng.gauss(450 * skill * win_bonus, 50); lh = rng.gauss(150 * win_bonus, 30)
        k, d, a = rng.gauss(6, 2), rng.gauss(7, 2), rng.gauss(15, 4)
    elif role == "Support":
        gpm = rng.gauss(320 * skill * win_bonus, 40); lh = rng.gauss(60, 20)
        k, d, a = rng.gauss(4, 2), rng.gauss(8, 2), rng.gauss(18, 4)
    else:  # HardSupport
        gpm = rng.gauss(280 * skill * win_bonus, 40); lh = rng.gauss(40, 15)
        k, d, a = rng.gauss(3, 1.5), rng.gauss(9, 2), rng.gauss(20, 5)
    return {
        "gpm": max(150, round(gpm)), "xpm": max(150, round(gpm * rng.uniform(0.9, 1.1))),
        "lh": max(10, round(lh)),
        "k": max(0, round(k)), "d": max(1, round(d)), "a": max(0, round(a)),
    }


def _write(out_dir, name, rows):
    with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    print("Generated Dota2 sample:", generate(os.path.join(here, "data")))
