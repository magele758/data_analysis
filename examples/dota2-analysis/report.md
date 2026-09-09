# Dota 2 战队与选手分析报告

> 由 data-analysis-service 端到端生成（SQL/OLAP · 相关性 · KMeans 打法聚类 · Insight Copilot）。数据结构对齐 OpenDota。

## 1. 战队战绩总览
| team | games | wins | winrate | avg_duration_min |
|---|---|---|---|---|
| Team Bravo | 38 | 30 | 78.9 | 42.9 |
| Team Cobra | 39 | 23 | 59.0 | 32.7 |
| Team Alpha | 38 | 22 | 57.9 | 34.2 |
| Team Delta | 50 | 25 | 50.0 | 39.7 |
| Team Falcon | 37 | 18 | 48.6 | 41.9 |
| Team Echo | 43 | 18 | 41.9 | 35.5 |
| Team Ghost | 34 | 11 | 32.4 | 33.4 |
| Team Hydra | 41 | 13 | 31.7 | 40.9 |

- 联赛对局时长中位数：**39.7 min**（节奏型/发育型分界）

## 2. 选手经验与数据（Top by GPM）
| player_name | team | role | games | kda | gpm | xpm | lh | hero_pool_size | winrate |
|---|---|---|---|---|---|---|---|---|---|
| Alp_Car | Team Alpha | Carry | 38 | 3.3 | 494.0 | 494.0 | 292.0 | 4 | 57.9 |
| Alp_Mid | Team Alpha | Mid | 38 | 3.5 | 490.0 | 497.0 | 237.0 | 3 | 57.9 |
| Bra_Mid | Team Bravo | Mid | 38 | 3.8 | 425.0 | 418.0 | 241.0 | 3 | 78.9 |
| Bra_Car | Team Bravo | Carry | 38 | 3.7 | 416.0 | 420.0 | 312.0 | 3 | 78.9 |
| Cob_Car | Team Cobra | Carry | 39 | 3.5 | 366.0 | 361.0 | 295.0 | 4 | 59.0 |
| Del_Car | Team Delta | Carry | 50 | 3.7 | 343.0 | 340.0 | 286.0 | 2 | 50.0 |
| Alp_Off | Team Alpha | Offlane | 38 | 3.0 | 334.0 | 335.0 | 159.0 | 3 | 57.9 |
| Del_Mid | Team Delta | Mid | 50 | 3.6 | 331.0 | 333.0 | 228.0 | 4 | 50.0 |
| Cob_Mid | Team Cobra | Mid | 39 | 3.4 | 324.0 | 322.0 | 243.0 | 2 | 59.0 |
| Bra_Off | Team Bravo | Offlane | 38 | 2.9 | 315.0 | 313.0 | 159.0 | 2 | 78.9 |
| Ech_Car | Team Echo | Carry | 43 | 3.0 | 308.0 | 301.0 | 278.0 | 4 | 41.9 |
| Ech_Mid | Team Echo | Mid | 43 | 3.5 | 289.0 | 291.0 | 240.0 | 4 | 41.9 |

## 3. 战队招牌英雄（习惯）
- **Team Bravo**：Spectre, Tidehunter, Io
- **Team Cobra**：Storm Spirit, Lina, Witch Doctor
- **Team Alpha**：Crystal Maiden, Underlord, Invoker
- **Team Delta**：Witch Doctor, Spectre, Faceless Void
- **Team Falcon**：Tidehunter, Invoker, Juggernaut
- **Team Echo**：Shadow Shaman, Jakiro, Treant Protector

## 4. 关键相关性（表现 ↔ 胜负）
- **gpm ↔ xpm**：r=0.9895（Very Strong）

## 5. 选手打法聚类 (KMeans)
- 自动最优簇数 k=**2**，轮廓系数 0.4304

## 6. 自动洞察 (Insight Copilot)
**【数据故事 · player_matches】1600 行，数据质量 100/100。**

- 相关性：「gpm」与「xpm」呈 Very Strong 相关（r=0.9895, p=0.0）。
- 异常：「gpm」检出 10 个离群点（均值 250.0, 标准差 104.19），需关注数据质量或业务突发。 「xpm」检出 10 个离群点（均值 249.54, 标准差 105.05），需关注数据质量或业务突发。 「assists」检出 4 个离群点（均值 14.6, 标准差 5.69），需关注数据质量或业务突发。 「deaths」检出 2 个离群点（均值 7.1, 标准差 2.49），需关注数据质量或业务突发。 「kills」检出 1 个离群点（均值 6.47, 标准差 3.64），需关注数据质量或业务突发。
- 洞察关联：i5↔i3（shares:gpm）；i5↔i4（shares:xpm）。多条洞察围绕同一指标/维度，提示存在共同的业务驱动因子，可进一步做归因下钻。
- **建议**：优先关注「gpm 与 xpm Very Strong 相关 (r=0.9895)」（严重度 0.99），建议用 driver_attribution_analysis 对相关指标做因子级归因。

## 7. 战术指导 (Tactical Guidance)
- **Team Bravo**（胜率 78.9% · 均时长 42.9min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Spectre, Tidehunter。
- **Team Cobra**（胜率 59.0% · 均时长 32.7min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Storm Spirit, Lina。
- **Team Alpha**（胜率 57.9% · 均时长 34.2min）：早期节奏型（平均时长偏短）：建议前期抱团压制、封野入侵、抢符抢盾，避免被拖入后期。 优先 ban 招牌英雄：Crystal Maiden, Underlord。
- **Team Delta**（胜率 50.0% · 均时长 39.7min）：后期发育型（平均时长偏长）：建议速推分带、压制打钱节奏、逼其提前团战。 优先 ban 招牌英雄：Witch Doctor, Spectre。
- **核心威胁（经济）**：优先 gank/切入 → Alp_Car(Team Alpha/Carry, GPM 494.0)；Alp_Mid(Team Alpha/Mid, GPM 490.0)；Bra_Mid(Team Bravo/Mid, GPM 425.0)。
- **核心威胁（KDA）**：Gho_Car(KDA 4.16)；Bra_Mid(KDA 3.75)；Del_Car(KDA 3.74)。
- **可预测的窄英雄池选手**（针对性 ban）：Hyd_Har（池 2）；Del_Har（池 2）；Ech_Sup（池 2）；Hyd_Car（池 2）；Alp_Sup（池 2）。

