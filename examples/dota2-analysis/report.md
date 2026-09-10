# Dota 2 战队与选手分析报告

> 由 data-analysis-service 端到端生成（SQL/OLAP · 相关性 · KMeans 打法聚类 · Insight Copilot）。数据结构对齐 OpenDota。

## 1. 战队战绩总览
| team | games | wins | winrate | avg_duration_min |
|---|---|---|---|---|
| Team Cobra | 36 | 28 | 77.8 | 43.5 |
| Team Bravo | 44 | 25 | 56.8 | 32.7 |
| Team Alpha | 30 | 16 | 53.3 | 40.9 |
| Team Falcon | 42 | 22 | 52.4 | 32.2 |
| Xtreme Gaming | 33 | 17 | 51.5 | 33.9 |
| Team Echo | 25 | 12 | 48.0 | 41.5 |
| Team Ghost | 32 | 14 | 43.8 | 38.3 |
| Team Delta | 36 | 13 | 36.1 | 32.8 |
| Team Hydra | 42 | 13 | 31.0 | 34.9 |

- 联赛对局时长中位数：**34.9 min**（节奏型/发育型分界）

## 2. 选手经验与数据（Top by GPM）
| player_name | team | role | games | kda | gpm | xpm | lh | hero_pool_size | winrate |
|---|---|---|---|---|---|---|---|---|---|
| Gam_Car | Xtreme Gaming | Carry | 33 | 4.0 | 525.0 | 529.0 | 294.0 | 4 | 51.5 |
| Gam_Mid | Xtreme Gaming | Mid | 33 | 3.6 | 503.0 | 499.0 | 229.0 | 3 | 51.5 |
| Alp_Car | Team Alpha | Carry | 30 | 2.8 | 433.0 | 435.0 | 295.0 | 3 | 53.3 |
| Alp_Mid | Team Alpha | Mid | 30 | 3.7 | 424.0 | 424.0 | 230.0 | 3 | 53.3 |
| Cob_Car | Team Cobra | Carry | 36 | 3.7 | 415.0 | 414.0 | 308.0 | 2 | 77.8 |
| Bra_Car | Team Bravo | Carry | 44 | 3.7 | 401.0 | 406.0 | 297.0 | 4 | 56.8 |
| Cob_Mid | Team Cobra | Mid | 36 | 3.5 | 392.0 | 388.0 | 246.0 | 4 | 77.8 |
| Bra_Mid | Team Bravo | Mid | 44 | 3.6 | 372.0 | 369.0 | 245.0 | 2 | 56.8 |
| Gam_Off | Xtreme Gaming | Offlane | 33 | 3.0 | 365.0 | 367.0 | 155.0 | 3 | 51.5 |
| Del_Mid | Team Delta | Mid | 36 | 3.6 | 341.0 | 339.0 | 221.0 | 4 | 36.1 |
| Del_Car | Team Delta | Carry | 36 | 3.7 | 339.0 | 342.0 | 274.0 | 4 | 36.1 |
| Alp_Off | Team Alpha | Offlane | 30 | 3.0 | 328.0 | 324.0 | 164.0 | 2 | 53.3 |

## 3. 战队招牌英雄（习惯）
- **Team Cobra**：Faceless Void, Witch Doctor, Treant Protector
- **Team Bravo**：Storm Spirit, Io, Lina
- **Team Alpha**：Tidehunter, Treant Protector, Storm Spirit
- **Team Falcon**：Puck, Axe, Witch Doctor
- **Xtreme Gaming**：Crystal Maiden, Witch Doctor, Rubick
- **Team Echo**：Tidehunter, Medusa, Mars

## 4. 关键相关性（表现 ↔ 胜负）
- **gpm ↔ xpm**：r=0.9904（Very Strong）

## 5. 选手打法聚类 (KMeans)
- 自动最优簇数 k=**2**，轮廓系数 0.4318

## 6. 自动洞察 (Insight Copilot)
**【数据故事 · player_matches】1600 行，数据质量 100/100。**

- 相关性：「gpm」与「xpm」呈 Very Strong 相关（r=0.9904, p=0.0）。
- 异常：「gpm」检出 10 个离群点（均值 261.15, 标准差 111.03），需关注数据质量或业务突发。 「xpm」检出 10 个离群点（均值 261.25, 标准差 112.22），需关注数据质量或业务突发。 「kills」检出 6 个离群点（均值 6.38, 标准差 3.52），需关注数据质量或业务突发。 「assists」检出 3 个离群点（均值 14.56, 标准差 5.69），需关注数据质量或业务突发。 「deaths」检出 2 个离群点（均值 6.98, 标准差 2.44），需关注数据质量或业务突发。
- 洞察关联：i5↔i3（shares:gpm）；i5↔i4（shares:xpm）。多条洞察围绕同一指标/维度，提示存在共同的业务驱动因子，可进一步做归因下钻。
- **建议**：优先关注「gpm 与 xpm Very Strong 相关 (r=0.9904)」（严重度 0.99），建议用 driver_attribution_analysis 对相关指标做因子级归因。

## 7. 战术指导 (Tactical Guidance)
- **Team Cobra**（胜率 77.8% · 均时长 43.5min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Faceless Void, Witch Doctor。
- **Team Bravo**（胜率 56.8% · 均时长 32.7min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Storm Spirit, Io。
- **Team Alpha**（胜率 53.3% · 均时长 40.9min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Tidehunter, Treant Protector。
- **Team Falcon**（胜率 52.4% · 均时长 32.2min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Puck, Axe。
- **核心威胁（经济）**：优先 gank/切入 → Gam_Car(Xtreme Gaming/Carry, GPM 525.0)；Gam_Mid(Xtreme Gaming/Mid, GPM 503.0)；Alp_Car(Team Alpha/Carry, GPM 433.0)。
- **核心威胁（KDA）**：Gam_Car(KDA 3.96)；Ech_Mid(KDA 3.89)；Fal_Mid(KDA 3.81)。
- **可预测的窄英雄池选手**（针对性 ban）：Gho_Har（池 2）；Bra_Mid（池 2）；Hyd_Sup（池 2）；Cob_Car（池 2）；Cob_Har（池 2）。

