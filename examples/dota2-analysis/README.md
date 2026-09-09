# Dota 2 战队与选手分析示例

用本仓库的 **data-analysis-service** 分析 Dota 2 职业比赛数据：统计战队战绩、选手经验与习惯（英雄池、打法），并产出**数据报告 + 战术指导**。

## 跑起来

```bash
cd examples/dota2-analysis
python generate_sample_data.py     # 生成 data/*.csv（种子固定，可复现）
python analyze_dota2.py            # 端到端分析 → report.md
```

`analyze_dota2.py` 会把比赛/选手数据载入内存会话，然后：
1. **SQL/OLAP**：战队战绩（场次/胜率/平均时长）、选手数据（KDA/GPM/XPM/英雄池大小/胜率）、战队招牌英雄；
2. **相关性**：表现指标与胜负的相关；
3. **KMeans 打法聚类**：按 gpm/xpm/kills/assists/last_hits 聚类选手风格；
4. **Insight Copilot**：结构化洞察 + 洞察图谱 + 叙事；
5. **战术指导（规则化）**：由上面算出的统计推导——节奏型/发育型定位、招牌英雄 ban 目标、核心威胁选手、可预测的窄英雄池选手。

全程进程内直接调用服务算子，无需起服务、无需鉴权。

## 数据结构（对齐 OpenDota 公开数据）

| 表 | 关键列 | 对应 OpenDota |
|---|---|---|
| `matches.csv` | match_id, start_date, duration_min, radiant_team, dire_team, winner, league | `/proMatches`, `/matches/{id}` |
| `player_matches.csv` | match_id, account_id, player_name, team, hero, role, kills, deaths, assists, gpm, xpm, last_hits, win | `/matches/{id}.players[]`, `/teams/{id}/players` |
| `teams.csv` | team_id, name, skill, style | `/teams`, `/teams/{id}` |

## 换成真实 OpenDota 数据

样本是合成的（可离线复现）。真实数据来自 **OpenDota API**（`https://api.opendota.com/api`，公开、免费、无需鉴权，有限速）：

- 职业比赛：`GET /proMatches`
- 单场详情（含 10 名选手数据）：`GET /matches/{match_id}`
- 战队：`GET /teams`、`GET /teams/{team_id}/matches`、`GET /teams/{team_id}/players`、`GET /teams/{team_id}/heroes`
- 选手：`GET /players/{account_id}`、`/players/{account_id}/matches`、`/players/{account_id}/heroes`

抓取示例（伪代码，需联网）：

```python
import requests, csv
pro = requests.get("https://api.opendota.com/api/proMatches").json()
for m in pro[:200]:
    detail = requests.get(f"https://api.opendota.com/api/matches/{m['match_id']}").json()
    # 展开 detail["players"] → player_matches 行；hero_id 用 dotaconstants 映射为英雄名
```

英雄 ID→英雄名、role/lane 解析可用 [dotaconstants](https://github.com/odota/dotaconstants)。也可用历史 **OpenDota 数据转储**（PostgreSQL 表 `matches`/`player_matches`）批量导入。把抓到的数据写成上表三张 CSV，`analyze_dota2.py` 即可直接分析。

## 报告包含

战队战绩总览、选手经验与数据、战队招牌英雄、关键相关性、KMeans 打法聚类、Insight Copilot 洞察，以及一段**可执行的战术指导**（针对每支强队的 ban/pick 与打法建议、核心威胁选手、窄英雄池针对）。
