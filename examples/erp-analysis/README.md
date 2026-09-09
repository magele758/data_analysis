# ERP 企业数据分析示例

用本仓库的 **data-analysis-service** 对一家企业的 ERP（订单到收款，Order-to-Cash）数据做端到端分析，产出一份 Markdown 数据报告。

## 跑起来

```bash
cd examples/erp-analysis
python generate_sample_data.py      # 生成 data/*.csv（种子固定，可复现）
python analyze_erp.py               # 端到端分析 → report.md
```

`analyze_erp.py` 若发现 `data/` 缺失会自动生成样本，然后：
1. 把 4 张 ERP 表载入内存 DuckDB 会话，JOIN 成销售事实表 `erp_sales`；
2. 依次调用服务算子：**EDA 画像 → OLAP（区域×品类）→ 数据质量断言 → 相关性 → 单因素 ANOVA → RFM 客户分群 → 环比归因（Driver Attribution）→ Insight Copilot（洞察+图谱+叙事）**；
3. 写出 `report.md`。

全程**进程内直接调用**服务算子，无需起服务、无需鉴权。（也可改造成走 REST `/api/v1/*`。）

## 数据结构（对齐真实 Kaggle ERP 数据集）

| 表 | 关键列 |
|---|---|
| `customers.csv` | customer_id, name, industry, segment, region |
| `products.csv` | product_id, name, category, unit_cost, unit_price |
| `sales_orders.csv` | order_id, customer_id, order_date, channel, status, region |
| `sales_order_lines.csv` | line_id, order_id, product_id, quantity, unit_price, discount, line_total, cogs, profit |

## 换成真实 Kaggle 数据

样本是合成的（可离线复现）。要用真实企业数据，推荐以下开源 ERP/供应链数据集：

- **`fares279/messyops`** — 17 张关系表，模拟中小 B2B 分销商两年的 Order-to-Cash + Procure-to-Pay（含 `sales_orders`/`sales_order_lines`/`products`/`customers`/`suppliers`/`invoices`/`payments`…），最贴近真实 ERP。
- **`ayodejiibrahimlateef/supply-chain-datasets`** — `customer_master`/`product_master`/`sales_orders`/`procurement_orders`/`supplier_master`。
- **`saicharankomati/dataco-supply-chain-dataset`** — 单表 ~18 万条供应链交易。

```bash
pip install kaggle                       # 需在 ~/.kaggle/kaggle.json 配置凭证
kaggle datasets download -d fares279/messyops -p data --unzip
```

下载后把真实文件列名映射到上表 4 张表的列名（或直接改 `analyze_erp.py` 里 `_load_session` 的建表 SQL 指向真实 CSV）。MessyOps 的 `sales_orders.csv` / `sales_order_lines.csv` 基本可直接用，`products`/`customers` 同名映射即可。

## 报告包含

数据概览与质量分、区域×品类销售利润排行、关键相关性、区域利润 ANOVA、RFM 客户分群、2024→2025 利润环比归因（自动定位主导拖累因子）、以及 Insight Copilot 的结构化洞察 + 洞察图谱 + 数据叙事与行动建议。
