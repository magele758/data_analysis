# Dota 2 战队与选手分析报告

> 由 data-analysis-service 端到端生成（SQL/OLAP · 相关性 · KMeans 打法聚类 · Insight Copilot）。数据结构对齐 OpenDota。
> 数据来源：OpenDota API (https://api.opendota.com) · 战队：Xtreme Gaming（team_id=8261500）· **数据获取日期：2026-09-10 UTC**

## 1. 战队战绩总览
| team | games | wins | winrate | avg_duration_min |
|---|---|---|---|---|
| Team Resilience | 2 | 2 | 100.0 | 34.9 |
| Team Falcons | 3 | 3 | 100.0 | 47.4 |
| Team Yandex | 1 | 1 | 100.0 | 46.9 |
| BoomBoys | 3 | 3 | 100.0 | 28.5 |
| PVISION | 1 | 1 | 100.0 | 31.1 |
| Aurora Gaming | 1 | 1 | 100.0 | 44.4 |
| LGD Gaming | 4 | 3 | 75.0 | 48.9 |
| Iron Wing | 4 | 3 | 75.0 | 55.2 |
| Team Liquid | 6 | 4 | 66.7 | 59.5 |
| Team Spirit | 3 | 2 | 66.7 | 49.2 |
| _PowerRangers | 2 | 1 | 50.0 | 40.7 |
| GamerLegion | 4 | 2 | 50.0 | 44.5 |
| Rune Eaters | 2 | 1 | 50.0 | 52.4 |
| Xtreme Gaming | 40 | 13 | 32.5 | 47.2 |
| HULIGANI | 2 | 0 | 0.0 | 43.6 |
| OG | 1 | 0 | 0.0 | 45.3 |
| GLYPH | 1 | 0 | 0.0 | 48.9 |

- 联赛对局时长中位数：**46.9 min**（节奏型/发育型分界）

## 2. 选手经验与数据（Top by GPM）
| player_name | team | role | games | kda | gpm | xpm | lh | hero_pool_size | winrate |
|---|---|---|---|---|---|---|---|---|---|
| Nightfall | Aurora Gaming | Carry | 1 | 32.0 | 982.0 | 1,131.0 | 750.0 | 1 | 100.0 |
| YSR-04E | Team Resilience | Carry | 2 | 20.5 | 833.0 | 999.0 | 475.0 | 2 | 100.0 |
| Satanic | PVISION | Carry | 1 | 8.0 | 823.0 | 869.0 | 459.0 | 1 | 100.0 |
| skiter | Team Falcons | Carry | 3 | 10.8 | 810.0 | 893.0 | 533.0 | 2 | 100.0 |
| 医者watson` | Team Yandex | Carry | 1 | 21.0 | 804.0 | 1,028.0 | 586.0 | 1 | 100.0 |
| 33 | Iron Wing | Carry | 1 | 7.2 | 796.0 | 992.0 | 923.0 | 1 | 100.0 |
| Yatoro | Team Spirit | Carry | 3 | 5.9 | 785.0 | 959.0 | 638.0 | 2 | 66.7 |
| 33 | Iron Wing | Offlane | 3 | 7.2 | 785.0 | 952.0 | 641.0 | 3 | 66.7 |
| Pure | Iron Wing | Offlane | 1 | 6.0 | 783.0 | 930.0 | 639.0 | 1 | 100.0 |
| JACKBOYS | GLYPH | Carry | 1 | 1.2 | 782.0 | 598.0 | 760.0 | 1 | 0.0 |
| Wisper | LGD Gaming | Offlane | 4 | 8.6 | 777.0 | 974.0 | 608.0 | 3 | 75.0 |
| m1CKe | Team Liquid | Carry | 6 | 5.1 | 774.0 | 960.0 | 692.0 | 4 | 66.7 |

## 3. 战队招牌英雄（习惯）
- **Team Resilience**：Mirana, Invoker, Doom
- **Team Falcons**：Clockwerk, Ember Spirit, Windranger
- **Team Yandex**：Invoker, Hoodwink, Lich
- **BoomBoys**：Winter Wyvern, Largo, Ringmaster
- **PVISION**：Treant Protector, Slardar, Viper
- **Aurora Gaming**：Axe, Nature's Prophet, Ember Spirit

## 4. 关键相关性（表现 ↔ 胜负）
- **gpm ↔ xpm**：r=0.8858（Very Strong）
- **gpm ↔ last_hits**：r=0.89（Very Strong）
- **xpm ↔ kills**：r=0.7334（Strong）
- **xpm ↔ last_hits**：r=0.7741（Strong）

## 5. 选手打法聚类 (KMeans)
- 自动最优簇数 k=**2**，轮廓系数 0.4079

## 6. 自动洞察 (Insight Copilot)
**【数据故事 · player_matches】400 行，数据质量 100/100。**

- 相关性：「gpm」与「xpm」呈 Very Strong 相关（r=0.8858, p=0.0）。 「kills」与「xpm」呈 Strong 相关（r=0.7334, p=0.0）。
- 异常：「kills」检出 4 个离群点（均值 5.03, 标准差 3.94），需关注数据质量或业务突发。 「assists」检出 4 个离群点（均值 12.12, 标准差 6.95），需关注数据质量或业务突发。 「deaths」检出 2 个离群点（均值 5.1, 标准差 3.14），需关注数据质量或业务突发。
- 洞察关联：i4↔i3（shares:xpm）；i3↔i0（shares:kills）。多条洞察围绕同一指标/维度，提示存在共同的业务驱动因子，可进一步做归因下钻。
- **建议**：优先关注「gpm 与 xpm Very Strong 相关 (r=0.8858)」（严重度 0.886），建议用 driver_attribution_analysis 对相关指标做因子级归因。

## 7. 战术指导 (Tactical Guidance)
- **Team Resilience**（胜率 100.0% · 均时长 34.9min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Mirana, Invoker。
- **Team Falcons**（胜率 100.0% · 均时长 47.4min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Clockwerk, Ember Spirit。
- **Team Yandex**（胜率 100.0% · 均时长 46.9min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Invoker, Hoodwink。
- **BoomBoys**（胜率 100.0% · 均时长 28.5min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Winter Wyvern, Largo。
- **核心威胁（经济）**：优先 gank/切入 → Nightfall(Aurora Gaming/Carry, GPM 982.0)；YSR-04E(Team Resilience/Carry, GPM 833.0)；Satanic(PVISION/Carry, GPM 823.0)。
- **核心威胁（KDA）**：Nightfall(KDA 32.0)；Mikoto(KDA 28.0)；niu(KDA 23.5)。
- **可预测的窄英雄池选手**（针对性 ban）：Echozz（池 2）；planet（池 1）；Mirage`雨（池 2）；RESPECT（池 1）；Bignum（池 2）。

