# 企业级现代数据技术栈 (MDS) 全链路智能数据服务与分析引擎

基于 **DuckDB 向量化计算引擎**、**Apache Arrow 零拷贝内存通信** 与 **OpenTelemetry 统一遥测规范** 打造的企业级 Modern Data Stack (MDS) 全闭环数据智能平台。
提供 **Data Catalog 数据资产与血缘**、**dbt 风格 ELT 数据清洗与 DAG 建模**、**专业统计检验与多维归因**、**Reverse ETL 数据激活与告警** 以及 **全链路交互式治理看板**。
全套核心算法 **100% 本地自研实现，零外部重型 SaaS 依赖**。

---

## 🌟 现代数据技术栈 (MDS) 全功能特性

### 1. Data Catalog 与统一指标语义层 (`app/catalog/`)
* **资产目录与字典**：自动沉淀表/字段业务含义、语义类型（MEASURE/DIMENSION）与标签。
* **数据血缘追踪 (Data Lineage)**：基于 SQL AST 解析，自动构建表级与列级有向依赖图谱与下游影响面分析。
* **统一指标语义库 (Metric Store)**：声明式定义标准化业务指标，自动编译为标准 DuckDB 执行 SQL。

### 2. ETL / ELT 转换与建模引擎 (`app/transform/`)
* **自动化数据清洗**：去重、空值智能填充（均值/中位数/众数/常数）、极值缩尾截断、类型强制转换。
* **dbt-like SQL DAG 编排**：基于 Kahn 拓扑排序算法，自动解析模型依赖关系，检测循环依赖并分层物化。
* **增量物化与宽表构建器**：支持内存视图、全量物化表与星型模型维度关联。

### 3. 专业数理统计、异动归因与自动化洞察
* **SPSS 级假设检验**：独立/配对 t 检验（Levene 方差齐性与 Welch 校正）、单/双因素 ANOVA + Tukey HSD、卡方独立性检验。
* **计量经济学回归**：OLS 多元回归全报告（$R^2$、F检验、VIF 多重共线性预警、Durbin-Watson 残差检验）。
* **波动下钻归因**：差异分解树 + Shapley 贡献率算法，自动输出瀑布图。
* **数据挖掘与洞察**：3-Sigma/孤立森林异常点检测、时序突变拐点、基尼/帕累托集中度、KMeans 聚类与 RFM 客户价值模型。

### 4. Reverse ETL 与业务数据激活 (`app/retl/`)
* **目标数据库反向同步**：将分析结果与分群标签反向写回外部 PostgreSQL、MySQL、SQL Server、SQLite 或 Parquet/CSV。
* **受众用户群导出**：提取 VIP 客户、流失预警群体，导出为标准 CSV/JSON 对接业务 CRM。
* **多平台告警下发**：支持一键向 **飞书机器人（富文本卡片）、企业微信、钉钉或标准 Webhook** 推送指标异动归因告警。

### 5. 数据可观测性与质量断言 (`app/observability/`)
* **声明式数据质量断言 (Great-Expectations 风格)**：非空率、唯一性、数值范围与行数波动断言，输出健康评分。
* **Schema 漂移检测**：自动比对上游表结构变更，提供阻断保护。

### 6. 前端遥测 SDK 与全功能治理看板 (`/dashboard`)
* **OpenTelemetry 前端采集 SDK (`sdk/browser-tracker/`)**：自动生成 W3C Trace Context，无埋点采集 PV/UV、点击、Web Vitals、JS 异常与**操作路径面包屑序列**。
* **全功能看板门户**：大盘概览、数据资产与血缘图、DAG 建模执行、Reverse ETL 激活、数据质量监控、Trace 瀑布流、操作路径复现、转化漏斗、流动桑基图、留存热力矩阵。

---

## 🚀 快速启动指南

### 1. 启动后端服务 (FastAPI + 看板)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

* **MDS 全功能分析与治理看板**：`http://localhost:8000/dashboard`
* **前端采集 SDK 联调测试页**：`http://localhost:8000/sdk/browser-tracker/index.html`
* **OpenAPI 交互式文档**：`http://localhost:8000/docs`

### 2. 启动 FastMCP Server
```bash
python -m app.mcp_server
```

#### 在 Claude Desktop / Cursor 中配置 (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "data-analysis-service": {
      "command": "/path/to/data-analysis-service/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/data-analysis-service"
      }
    }
  }
}
```

---

## 🧪 运行自动化测试
```bash
pytest tests/ -v
```
