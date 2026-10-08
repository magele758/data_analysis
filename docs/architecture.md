# 系统深度架构设计说明书 (System Architecture & Technical Foundations)

## 1. 架构总览

本服务是**单机数据分析服务**：一个进程里的 DuckDB 会话，加上语义层、本体和统计算子，给 AI Agent（如 Claude、Cursor、Dify、AutoGen）调用。

```
+-------------------------------------------------------------------------+
|                  External Agent (Claude / Cursor / Dify)               |
+-------------------------------------------------------------------------+
                                    |  (MCP tools / REST /api/v1)
                                    v
+-------------------------------------------------------------------------+
|                         Interface Layer                                 |
|  - FastMCP Server (STDIO / SSE HTTP)                                    |
|  - FastAPI RESTful Endpoints (/api/v1/*)                                |
|  - Modern Data Stack Web Dashboard (/dashboard)                         |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|                   Modern Data Stack (MDS) Engines                       |
|  1. Data Catalog & Semantic Layer: MetaRegistry, Lineage, MetricStore   |
|  2. ETL / ELT Transformation: DataCleaner, PipelineDAG, Materializer    |
|  3. Reverse ETL & Activation: DestinationSync, AudienceExporter, Alert  |
|  4. Observability: DataQualityAssertions, SchemaDrifter                 |
|  5. Local NLG Narrative Engine & Vega-Lite / ECharts Spec Builder       |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
|           Single-process in-memory compute (this process)              |
|  - One DuckDB connection per session, C++ vectorized engine             |
|  - Apache Arrow zero-copy register                                      |
|  - Scipy / Statsmodels / Sklearn on the aggregated rows                 |
|  - Spill under MAX_MEMORY_PER_SESSION_MB; sessions stay on this process |
|  - KubeRay is not on this path (DEPLOY.md does not require Ray)         |
+-------------------------------------------------------------------------+
                                    ^
                                    | (load into the session connection)
+-------------------------------------------------------------------------+
|                    Connector & Ingestion Layer                          |
|  - Rust ConnectorX (PostgreSQL, MySQL, SQL Server, SQLite, Parquet)     |
|  - OpenTelemetry Frontend Tracker SDK (W3C Trace Context)               |
|  - CDC Streaming Consumer & In-Memory Ring Buffer                       |
+-------------------------------------------------------------------------+
```

---

## 2. 核心技术底座与高性能实现机制

### 2.1 零拷贝（Zero-Copy）内存管道
1. **网络提取阶段**：基于 Rust `connectorx` 直接在 C 级别将二进制通信协议解析为 **Apache Arrow RecordBatches**。
2. **内存分析阶段**：Arrow 内存块直接在 DuckDB 进程内以 C++ 视图注册，内存地址零拷贝直读。
3. **统计诊断阶段**：DuckDB 聚合出的汇总数组直接以连续内存指针传递给 `Numpy / Scipy / Statsmodels`。

### 2.2 dbt-style 本地轻量化 SQL DAG 编排 (PipelineDAG)
* 采用 **Kahn 拓扑排序算法**，自动解析模型之间的 `depends_on` 依赖关系。
* 自动检测循环依赖（Cycle Detection）并按依赖层级分层物化（`Staging -> DWD -> DWS/Marts`）。

### 2.3 单机会话内的充分统计量
* 运行中的服务就是图里这一台 DuckDB。KubeRay 不在这条进程的执行路径上，`DEPLOY.md` 也不要求 Ray。
* 相关、EDA 在这一条连接上做单遍聚合。表超过 10 万行时，distinct 用 `approx_count_distinct`。回归超过 40 个自变量或 500 万个单元格时，直接要求调用方先聚合。

### 2.4 反向 ETL 与数据激活闭环 (Reverse ETL)
* 将分析洞察结果（如 RFM 用户分群标签、时序预测数据）秒级反写至业务数据库，并支持一键向飞书/企业微信/Slack 推送富文本归因卡片。

### 2.5 会话内计算契约
* 每个会话一条 DuckDB 连接，内存上限是 `MAX_MEMORY_PER_SESSION_MB`，溢写目录在会话关闭时删除。连接串写入目录前会被打码。
* 算子结果带 evidence：`operator`、`method`、`sql`、扫描行数、使用行数、丢弃空值、耗时、caveats。调用方用这些字段叙述，不重新心算。
* SUM 归因是加法贡献。比率×数量是 Laspeyres 分解。相关矩阵附 Benjamini-Hochberg `q_value`。预测在全序列上拟合，另给一段留出 MAPE 与朴素基线比较。
* 语义层先在指标自己的表上聚合，再沿外键到主键连接。本体多跳遍历和动作预演（MCP `dry_run` 默认为真）走同一条连接。
