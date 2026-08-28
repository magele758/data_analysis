# 企业级现代数据栈 (MDS) 与 Palantir 风格 Agentic Ontology 智能分析引擎

基于 **DuckDB 向量化计算引擎**、**Apache Arrow 零拷贝内存通信** 与 **Palantir 业务本体 (Ontology) 架构** 打造的企业级现代数据智能平台。
提供 **Palantir 风格业务实体 (Objects)、关系拓扑 (Links) 与闭环动作 (Actions)**、**Data Catalog 数据资产与血缘**、**dbt 风格 ELT 数据清洗与 DAG 建模**、**专业统计检验与多维归因**、**Reverse ETL 数据激活与告警** 以及 **全链路交互式治理大盘**。
全套核心算法 **100% 本地自研实现，零外部重型 SaaS 依赖**。

---

## 🌟 核心功能矩阵 (25 个高信噪比 IQuery 语义算子)

### 1. Palantir 风格业务本体模型 (Agentic Ontology) (`app/ontology/`)
* **业务对象模型 (Object Types)**：将物理表映射为真实实体（`Customer`, `Order`, `Product`, `Device`），包含属性、主键与状态。
* **实体关系图谱 (Link Types)**：定义 $1:1$、$1:N$、$N:M$ 业务拓扑，支持 Agent 沿实体链执行**多跳图谱遍历与因果溯源**。
* **业务闭环动作 (Action Types)**：定义可逆、带参数校验的业务动作（如 `ApplyDiscountAction`, `RerouteOrderAction`），打通 Reverse ETL / Webhook 写回并记录完整**审计流水 (Audit Trail)**。

### 2. Data Catalog 与统一指标语义层 (`app/catalog/`)
* **资产目录与字典**：沉淀表/字段业务含义、语义类型与标签。
* **CTE 语法感知数据血缘 (Data Lineage)**：基于 SQL AST 解析，精确过滤内部 CTE 别名，自动构建表级依赖图谱与下游影响面分析。
* **统一指标语义库 (Metric Store)**：声明式定义标准化业务指标，自动编译为标准 DuckDB 执行 SQL。

### 3. ETL / ELT 转换与建模引擎 (`app/transform/`)
* **自动化数据清洗**：去重、空值智能填充（均值/中位数/众数/常数）、极值缩尾截断。
* **事务性与分层并行 SQL DAG 编排**：基于 Kahn 拓扑排序算法，同层模型并发物化，采用影子表原子切换（Staging Swap）与失败自动回滚。

### 4b. Insight Copilot（自动洞察发现编排层, `app/copilot/`）
* **`discover_insights`**：把 EDA/异常/相关/集中/趋势等确定性算子当作 **Analysis Actions** 编排，产出 ①排序后的结构化洞察 ②**洞察图谱 (Insight Graph)** ——洞察间关系网络 ③**数据叙事 (data story)**。可选 `intent` 轻量偏置要跑的动作。这是新一代自动洞察范式（InsightPilot / DataSage 风格）中**可本地确定性实现**的部分；语义意图理解与多智能体推理交给调用方 Agent（符合"算法本地自研、LLM 高层编排"的边界）。

### 4. 专业数理统计、异动归因与自动化洞察
* **SPSS 级假设检验**：独立/配对 t 检验（Levene 方差齐性与 Welch 校正）、单/双因素 ANOVA + Tukey HSD、卡方独立性检验。
* **计量经济学回归**：OLS 多元回归全报告（$R^2$、F检验、VIF 多重共线性预警、Durbin-Watson 残差检验）。
* **波动下钻归因**：差异分解树 + Shapley 贡献率算法，自动输出瀑布图。
* **数据挖掘与洞察**：3-Sigma/孤立森林异常点检测、时序突变拐点、基尼/帕累托集中度、KMeans 聚类与 RFM 客户价值模型。

### 5. Reverse ETL 与业务数据激活 (`app/retl/`)
* **目标数据库流式反向同步**：基于 Arrow 分块流式同步，将分析结果与分群标签反写回外部 PostgreSQL、MySQL、SQLite 或 Parquet/CSV。
* **受众用户群导出**：提取 VIP 客户、流失预警群体，导出为标准 CSV/JSON 对接业务 CRM。
* **带退避重试的告警推送**：支持向 **飞书机器人（富文本卡片）、企业微信、钉钉或标准 Webhook** 推送指标异动归因告警。

### 6. 数据可观测性与单遍扫描断言 (`app/observability/`)
* **单遍扫描数据质量断言 (Great-Expectations 风格)**：多规则动态合并为单次聚合 SQL，一次扫描完成非空、唯一、取值区间与行数校验。
* **Schema 漂移检测**：自动比对上游表结构变更，提供阻断保护。

### 7. 两条数据入口 → 一个分析引擎
本服务是「**DB 连接器 + trace 两条路的数据分析服务**」，两条路都落进同一个内存 DuckDB 会话，共用全部管道算子：
* **Path A · DB 连接器**：`connect_and_load_db` 接入 PostgreSQL/MySQL/MSSQL/SQLite/File，`import_excel_or_csv` 秒级导入大 Excel/CSV。
  * 两种抽取模式：`mode="materialize"`（默认，ConnectorX 物化）或 `mode="scanner"`（DuckDB 原生 `ATTACH` + 谓词/投影下推，PG/MySQL），后者少一层依赖、可把过滤下推到源库。
* **Path B · trace 导入**：`import_traces` 把 trace/遥测（OTLP JSON、span JSON/NDJSON、CSV/Parquet）作为**数据源**导入会话表，随后可对其运行 EDA/OLAP/SPSS/归因/漏斗/span 瀑布/质量断言/Reverse ETL —— 与 DB 路径同一套算子。
* trace 数据在导入时被规整为统一的 span/event schema。**本服务不自己做埋点采集**，采集是可选示例（见 `examples/telemetry-collector-demo/`），通过 `import_traces` 把数据喂进来。

### 8. 数据处理管道演示看板 (`/dashboard`)
按数据实际流向组织的六阶段管道：**摄取(Ingest) → 清洗(Transform) → 建模(Model) → 分析(Analyze) → 质量(Quality) → 激活(Activate)**，可一键在一个实时会话上跑通全链路。

---

## 🚀 快速启动指南

### 1. 启动后端服务 (FastAPI + 看板)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动服务（本地可信开发关闭鉴权；生产需配置 DATA_AGENT_API_KEYS）
DATA_AGENT_REQUIRE_AUTH=false uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

* **数据处理管道演示看板**：`http://localhost:8000/dashboard`
* **OpenAPI 交互式文档**：`http://localhost:8000/docs`

导入 trace 数据源示例：
```bash
curl -X POST http://localhost:8000/api/v1/import/traces \
  -H 'Content-Type: application/json' \
  -d '{"source":"traces.json","dataset_name":"traces","session_id":"s1"}'
# 之后即可对会话 s1 的 traces 表运行 EDA / 漏斗 / span 瀑布 / 质量断言 等

# 可选：遥测采集示例（独立于主服务）
#   cd examples/telemetry-collector-demo && uvicorn demo_server:app --port 8100

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
