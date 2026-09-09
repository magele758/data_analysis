# ERP 企业数据分析报告

> 由 data-analysis-service 端到端生成（EDA · OLAP · 质量 · 相关 · ANOVA · RFM · 归因 · Insight Copilot）。

## 1. 数据概览与质量
- 有效销售明细行：**4,103**（已过滤取消订单）
- 数据质量健康分：**100.0/100**，断言 4/4 通过
- EDA 画像：【数据资产画像】数据集共包含 4,103 行、16 列，综合数据质量评分为 100/100 分。 识别出连续度量指标 6 个（quantity, unit_price, discount, sales等），离散分类维度 5 个（region, channel, segment, industry等）。 ✅ 数据完整性良好，未发现异常缺失字段。

## 2. 区域 × 品类 销售与利润 (OLAP)
| region | category | sales_sum | profit_sum |
|---|---|---|---|
| North | Technology | 592,301.27 | 192,998.74 |
| South | Technology | 635,837.45 | 192,041.60 |
| East | Technology | 675,704.11 | 251,704.82 |
| West | Technology | 785,178.38 | 193,705.23 |
| South | Office Supplies | 524,900.28 | 75,235.26 |
| North | Office Supplies | 440,647.76 | 73,337.13 |
| West | Office Supplies | 664,575.21 | 92,266.94 |
| East | Office Supplies | 497,273.07 | 75,891.63 |
| East | Furniture | 704,502.00 | 139,954.51 |
| South | Furniture | 651,816.78 | 132,044.26 |

## 3. 关键相关性
- **sales ↔ profit**：r=0.8299（Strong）

## 4. 区域利润差异检验 (One-way ANOVA)
- 【SPSS 统计推断 - 接受原假设】One-Way ANOVA 结果未达到统计学显著性差异 (p=0.2383 >= 0.05)。 One-Way ANOVA across 4 levels of 'region': F(3, 4099) = 1.409, p = 0.238281, eta_squared = 0.001. The effect of 'region' on 'profit' is not significant.

## 5. 客户价值分群 (RFM)
- Champions (重要价值客户): 71
- Loyal Customers (重要保持客户): 102
- Potential Loyalists (重要发展客户): 77
- At Risk (重要挽留客户): 23
- Lost (流失客户): 31

## 6. 利润环比归因 (2024 → 2025，Driver Attribution)
- West: 贡献差异 -77,356.74
- East: 贡献差异 -63,192.10
- North: 贡献差异 62,759.92
- South: 贡献差异 -21,828.26
- 叙述：【异动归因分析】目标指标 'profit' 整体发生波动：下滑 99,617.18 (-11.02%)。 在维度 'region' 层级：主导负向拖累项为 'West' (变动 -77,356.74, 贡献率 77.65%)。 在维度 'category' 层级：主导负向拖累项为 'Technology' (变动 -73,251.50, 贡献率 73.53%)。

## 7. 自动洞察 (Insight Copilot)
**【数据故事 · erp_sales】4103 行，数据质量 100/100。**

- 相关性：「profit」与「sales」呈 Strong 相关（r=0.8299, p=0.0）。 「quantity」与「cogs」呈 Strong 相关（r=0.7289, p=0.0）。 「sales」与「cogs」呈 Strong 相关（r=0.7031, p=0.0）。
- 异常：「discount」检出 10 个离群点（均值 0.09, 标准差 0.07），需关注数据质量或业务突发。 「cogs」检出 10 个离群点（均值 1437.93, 标准差 1031.55），需关注数据质量或业务突发。 「profit」检出 5 个离群点（均值 416.38, 标准差 1314.86），需关注数据质量或业务突发。 「sales」检出 5 个离群点（均值 1854.31, 标准差 1816.54），需关注数据质量或业务突发。
- 洞察关联：i4↔i6（shares:sales）；i4↔i0（shares:profit）；i4↔i2（shares:sales）；i5↔i6（shares:cogs）；i5↔i3（shares:cogs）。多条洞察围绕同一指标/维度，提示存在共同的业务驱动因子，可进一步做归因下钻。

- 洞察图谱：7 节点 / 7 关系
- **建议**：优先关注「profit 与 sales Strong 相关 (r=0.8299)」（严重度 0.83），建议用 driver_attribution_analysis 对相关指标做因子级归因。
