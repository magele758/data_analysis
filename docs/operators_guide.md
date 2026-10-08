# 数据分析与业务本体算子指南 (25 Registered Operators)

本服务为 Agent 提供了 25 个高度抽象、高信噪比的 IQuery 语义算子，覆盖 Palantir Ontology 业务本体与现代数据栈全生命周期。

---

## 一、 Palantir 风格 Agentic Ontology 业务本体层

### 1. 本体元数据模式查询算子 (`ontology_list_schema`)
* **作用**：获取系统内已注册的所有业务对象模型（Object Types）、关系链路（Link Types）以及可执行动作（Action Types）。

### 2. 实体对象实例检索算子 (`ontology_query_objects`)
* **作用**：从底层 DuckDB 数据表中检索具体业务实体（如 `Customer`、`Order`），支持属性投影与动态过滤条件。

### 3. 实体关系多跳遍历算子 (`ontology_traverse_links`)
* **作用**：沿着实体拓扑关系链执行图遍历（如从客户 `C01` 出发，通过 `customer_orders` 遍历出所有关联订单）。返回 `path`、`hops` 和每一跳的 `hop_counts`。$N:M$ 经关联表连接，关联表字段会写入目录库。

### 4. 业务动作闭环执行算子 (`ontology_execute_action`)
* **作用**：执行业务实体上的原子动作。审计结果带执行前、执行后和 `statement_hash`。`REVERSE_ETL_SYNC` 在 `handler_config` 提供 `dest_conn_str`、`dest_table_name`、`source_table` 时调用 `DestinationSync`；缺配置时返回失败，不假装同步成功。MCP 默认 `dry_run=true`。

---

## 二、 数据接入与沙箱层

### 5. 数据库连接与加载算子 (`connect_and_load_db`)
* **作用**：连接外部 PostgreSQL / MySQL / SQL Server / SQLite / Parquet 文件，按需抽取并加载至当前 Session 内存空间，并自动登记至 Data Catalog。

### 6. DuckDB 安全 SQL 沙箱 (`duckdb_sql_sandbox`)
* **作用**：允许 Agent 直接下发原生 DuckDB SQL 表达复杂分析意图。只允许单条 SELECT/EXPLAIN，拒绝 `read_csv`、`read_parquet`、`postgres_scan` 等外部表函数，并在该条语句执行期间关闭 `enable_external_access`。指标编译出的 SQL 标记 `governed=true`；自由 SQL 标记 `ungoverned_sql=true`。

---

## 三、 资产目录与统一指标语义层

### 7. 统一指标语义查询算子 (`query_semantic_metric`)
* **作用**：根据 Semantic Metric Store 中标准化的指标公式与维度定义，自动编译为标准 DuckDB 执行 SQL 并返回结果。注册了语义模型时，指标先在自己的表上聚合，再沿外键指向主键做最多两跳多对一连接；一对多扇出会被拒绝。`CUMULATIVE` 指标沿模型的时间脊做累计。`RATIO` 先聚合分子指标、再聚合分母指标，然后相除，不会先对行比率取平均。查询响应带 `metric_versions`（公式、表、聚合方式的短哈希）和编译后的 SQL。配套工具：`register_semantic_metric`、`list_semantic_metrics`、`register_semantic_model`、`list_session_datasets`。未登记维度白名单时，编译仍接受调用方传入的维度。

---

## 四、 ETL / ELT 数据清洗与建模层

### 8. 自动化数据清洗算子 (`execute_data_cleaning`)
* **作用**：对指定数据表执行自动去重、空值填充（均值/中位数/众数/常数）、极值缩尾截断（Winsorization）。

### 9. dbt 风格 SQL DAG 建模调度算子 (`run_dag_pipeline`)
* **作用**：基于 Kahn 拓扑排序算法，按模型依赖顺序依次物化 DAG 管道中的所有模型，支持影子表原子替换与回滚。`view` 与 `ephemeral` 建成视图；`incremental` 在提供 `unique_key` 且目标表已存在时按键合并，否则整表刷新。同一条 DuckDB 连接上按阶段顺序执行。`depends_on` 留空时，用 SQL 血缘解析补上来源表；调用方显式传入的依赖不会被覆盖。

---

## 五、 核心数理统计、归因与自动洞察

### 10. EDA 探索性数据画像算子 (`eda_profile`)
* **作用**：一次聚合扫描输出空值、均值、标准差、分位数、偏度和峰度。语义类型仍来自前 5000 行样本，结果里写着 `type_inference_sample_rows`。表不超过 10 万行时 distinct 是精确计数；超过之后用 `approx_count_distinct`，并在列上标明 `distinct_count_method`。

### 11. 多维异动下钻与归因算子 (`driver_attribution_analysis`)
* **作用**：针对指标波动，沿维度层级路径逐层下钻。`SUM` 使用加法贡献，每一层子项差值之和等于总差值，并在结果里记录 `closes`。`AVG`/`COUNT`/`MIN`/`MAX` 只做水平对比，不声称闭合。同时传入 `rate_col` 与 `volume_col` 时，按 Laspeyres 恒等式拆成量效应、率效应和交互项（`structure_effect` 与交互项是同一个交叉项）。结果里的 `orderings_used` 是 1：按调用方给出的维度顺序下钻，不计算 Sun-Shapley。方法名写在 `method` 字段里。这不是 Shapley 值。

### 12. SPSS 级数理假设检验算子 (`spss_hypothesis_test`)
* **支持类型**：独立样本 t 检验（含 Levene 方差齐性与 Welch 校正）、配对样本 t 检验（`paired_t_test`，两个数值列）、单因素 ANOVA（含事后 Tukey HSD 与 eta^2）、双因素 ANOVA（`two_way_anova`，需要 `factor_b`，含交互项）、卡方独立性检验（含 Cramér's V）、Mann-Whitney U 检验。`significant` 同时要求 p 值过线，以及效应量过线：|Cohen's d| ≥ 0.2、η² ≥ 0.01、Cramér's V ≥ 0.1、|rank-biserial r| ≥ 0.1。

### 13. 多元回归与计量经济学诊断算子 (`spss_regression_analysis`)
* **支持模型**：OLS 多元线性回归（$R^2$、F检验、系数表、VIF 多重共线性诊断、Durbin-Watson 残差自相关检验）、二元 Logistic 回归。自变量超过 40 列，或扫描单元格超过 500 万时，返回「请先聚合再回归」，不把明细拉进进程。

### 14. 自动化洞察挖掘算子 (`detect_automated_insights`)
* **异常点 (Outliers)**：3-Sigma、IQR、孤立森林。
* **趋势与拐点 (Trends)**：线性回归斜率显著性检验 + 滑动窗口斜率突变拐点识别。
* **支配度 (Dominance)**：基尼系数（Gini）与帕累托 80/20 集中度。

### 15. 内存多维 OLAP 聚合算子 (`memory_olap_aggregation`)
* **作用**：多维切片切块（Slice & Dice）、Rollup 与 Cube 聚合。

### 实测：1000 万行上的 EDA 与相关

2026-10-08，在 Darwin 24.6.0 arm64、Python 3.13.2、DuckDB 1.5.5 上测了一次。会话 `bench_slice` 用 `range(10000000)` 建表 `bench10m`，列是 `id`、`x = i % 1000`、`y = i % 50`、`z = sin(i)`。EDA 和相关各起一个新进程。macOS 的 `ru_maxrss` 单位是字节，峰值包含这张表。建表约 0.20 秒，不在下表的算子耗时里。这是这一次测量，不是性能承诺。

| 算子 | 行数 | 耗时 | 进程峰值 RSS |
| --- | ---: | ---: | ---: |
| `DistributedEDA.profile_table` | 10,000,000 | 1.930 秒（evidence `duration_ms` 1930.06） | 3,229,220,864 字节（3079.6 MiB） |
| `run_correlation_analysis`（`x`,`y`,`z`，Pearson） | 10,000,000 | 0.010 秒（evidence `duration_ms` 10.14） | 568,754,176 字节（542.4 MiB） |

EDA 四列的 `distinct_count_method` 都是 `approx_count_distinct`，`rows_scanned` 为 10000000。相关的 `rows_scanned` 和 `sample_size` 也是 10000000，返回的 `high_correlation_pairs` 为 0。

---

## 六、 Trace / 用户行为分析（运行于会话内导入的 trace 表）

> 这些算子不再连独立的采集库；它们对**导入到分析会话的 trace 数据源**（经 `import_traces` 载入）运行，
> 因此与 DB 连接器路径共用同一分析引擎。每个算子入参含 `session_id` 与 `dataset_name`。
> trace 数据源经 `import_traces` 接入（OTLP JSON / span JSON/NDJSON / CSV / Parquet）。

### 16. 转化漏斗算子 (`analyze_conversion_funnel`)
* **入参**：`session_id`, `dataset_name`, `steps`, `date_from?`, `date_to?`
* **作用**：计算多步骤有序转化漏斗、各步骤留存人数、步进流失率与总转化率。

### 17. 用户流动与桑基图算子 (`analyze_user_flow`)
* **作用**：基于会话内页面访问时序生成 N-Gram 转移矩阵，输出 ECharts 桑基图 (Sankey) 拓扑。

### 18. 留存队列分析算子 (`analyze_cohort_retention`)
* **作用**：按首次活跃日期划分群组，计算 N 天活跃用户数与留存百分比热力图。

### 19. 页面深度分析算子 (`analyze_page_performance`)
* **作用**：计算页面 PV、UV、平均停留时长与跳出分析。

### 20. 链路追踪与操作路径复现 (`inspect_trace_and_replay`)
* **入参**：`session_id`, `dataset_name`, `trace_id?`, `telemetry_session_id?`
* **作用**：从会话内 trace 表构建 OpenTelemetry Span 瀑布流，按遥测 Session 还原用户点击与页面流转时间轴。

---

## 七、 反向 ETL 与数据激活层

### 21. 目标库反向同步算子 (`reverse_sync_destination`)
* **作用**：流式分块将分析结果或 RFM 分群标签反写回外部 PostgreSQL、MySQL、SQLite 或 Parquet/CSV。

### 22. 受众分群导出算子 (`export_audience_cohort`)
* **作用**：提取特定受众分群导出为 CSV/JSON 对接业务 CRM。

### 23. 智能告警推送算子 (`send_operational_webhook_alert`)
* **作用**：向飞书机器人（富文本卡片）、企业微信、钉钉或 Webhook 推送归因告警。

---

## 八、 数据可观测性与质量断言层

### 24. 声明式数据质量断言算子 (`assert_data_quality`)
* **作用**：单遍扫描运行 Great-Expectations 风格的数据质量断言（非空、唯一、数值区间、行数范围），输出健康总评分。

### 25. Schema 漂移检测算子 (`detect_table_schema_drift`)
* **作用**：自动比对字段增减与类型漂移，提供下游熔断保护。
