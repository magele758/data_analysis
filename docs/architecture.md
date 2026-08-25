# 系统深度架构设计说明书 (System Architecture & Technical Foundations)

## 1. 架构总览

本服务定位为**“企业级现代数据技术栈 (MDS) 全链路智能数据服务与分析引擎”**，专为 AI Agent（如 Claude、Cursor、Dify、AutoGen）提供高性能、高信噪比的语义化数据分析算子（IQuery）。

```
+-------------------------------------------------------------------------+
|                  External Agent (Claude / Cursor / Dify)               |
+-------------------------------------------------------------------------+
                                    |  (IQuery Protocol: 21 Registered Tools)
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
            +-----------------------+-----------------------+
            | (In-Memory Compute Engine)                    | (Distributed Compute)
            v                                               v
+------------------------------------+   +--------------------------------+
| Local In-Memory Compute Engine     |   | KubeRay Multi-Pod Cluster      |
| - DuckDB C++ Vectorized Engine     |   | - Ray Workers (HPA Scaled)     |
| - Apache Arrow Zero-Copy IPC       |   | - Arrow Flight gRPC Stream     |
| - Scipy / Statsmodels / Sklearn    |   | - Distributed Map-Reduce DAG   |
+------------------------------------+   +--------------------------------+
                                    ^
                                    | (Parallel Partition Ingestion)
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

### 2.3 分布式 Map-Reduce 充分统计量单遍扫描（Sufficient Statistics）
* Map 阶段各 Worker Pod 仅计算局部统计矩阵，Reduce 阶段在 Master 瞬间合并求解全局均值、方差、偏度、峰度、t 统计量、ANOVA 离差平方和与多元回归系数。

### 2.4 反向 ETL 与数据激活闭环 (Reverse ETL)
* 将分析洞察结果（如 RFM 用户分群标签、时序预测数据）秒级反写至业务数据库，并支持一键向飞书/企业微信/Slack 推送富文本归因卡片。
