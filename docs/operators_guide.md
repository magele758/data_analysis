# 数据分析与业务本体算子指南 (25 Registered Operators)

本服务为 Agent 提供了 25 个高度抽象、高信噪比的 IQuery 语义算子，覆盖 Palantir Ontology 业务本体与现代数据栈全生命周期。

---

## 一、 Palantir 风格 Agentic Ontology 业务本体层

### 1. 本体元数据模式查询算子 (`ontology_list_schema`)
* **作用**：获取系统内已注册的所有业务对象模型（Object Types）、关系链路（Link Types）以及可执行动作（Action Types）。

### 2. 实体对象实例检索算子 (`ontology_query_objects`)
* **作用**：从底层 DuckDB 数据表中检索具体业务实体（如 `Customer`、`Order`），支持属性投影与动态过滤条件。

### 3. 实体关系多跳遍历算子 (`ontology_traverse_links`)
* **作用**：沿着实体拓扑关系链执行图遍历（如从客户 `C01` 出发，通过 `customer_orders` 遍历出所有关联订单）。返回 `path`、`hops`、`hop_counts`、`hop_details`。某一跳碰到 `limit` 时 `truncated` 为真。对象查询的 `matched_count` 是过滤后的全量，`total_instances` 仍是本页行数。REST `POST /api/v1/ontology/instances/traverse` 把 `link_path` 和 `max_hops` 传给引擎。`GET /api/v1/ontology/entity_graph` 与 MCP `ontology_entity_graph` 返回 nodes、edges、broken_edges。$N:M$ 经关联表连接，关联表字段会写入目录库。

### 4. 业务动作闭环执行算子 (`ontology_execute_action`)
* **作用**：执行业务实体上的原子动作。审计结果带执行前、执行后和 `statement_hash`。Webhook 推送返回 `FAILED` 时审计也是 `FAILED`，即使结果里仍有 `simulated_payload`。`REVERSE_ETL_SYNC` 在 `handler_config` 提供 `dest_conn_str`、`dest_table_name`、`source_table` 时调用 `DestinationSync`；缺配置时返回失败，不假装同步成功。MCP `ontology_execute_action` 默认 `dry_run=true`。REST `POST /api/v1/ontology/actions/execute` 默认 `dry_run=false`。REST 遍历请求体带 `link_path` 和 `max_hops`。

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
* **作用**：基于 Kahn 拓扑排序算法，按模型依赖顺序依次物化 DAG 管道中的所有模型，支持影子表原子替换与回滚。`view` 与 `ephemeral` 建成视图；`incremental` 在提供 `unique_key` 且目标表已存在时按键合并，否则整表刷新。同一阶段的模型在同一条 DuckDB 连接上顺序执行，不是并发。`unique_key` 写入 `dag_models_meta`，重启后仍在。`depends_on` 留空时，用 SQL 血缘解析补上来源表；调用方显式传入的依赖不会被覆盖。宽表是 `POST /api/v1/transform/wide` 与 MCP `create_wide_table`，返回 `columns`。

---

## 五、 核心数理统计、归因与自动洞察

### 10. EDA 探索性数据画像算子 (`eda_profile`)
* **作用**：一次聚合扫描输出空值、均值、标准差、分位数、偏度和峰度。语义类型仍来自前 5000 行样本，结果里写着 `type_inference_sample_rows`。表不超过 10 万行时 distinct 是精确计数，分位数是 `quantile_cont`；超过之后 distinct 用 `approx_count_distinct`，分位数用 `approx_quantile`，列上分别标明 `distinct_count_method` 和 `quantile_method`。`quantile_method` 为 `quantile_cont` 时，p50 也来自 `quantile_cont`。度量列的 `skewness`、`kurtosis`、`std` 在矩未定义时为 null，不再写成 0。

### 11. 多维异动下钻与归因算子 (`driver_attribution_analysis`)
* **作用**：针对指标波动，沿维度层级路径逐层下钻。第一层分支会生成 Vega-Lite v5 瀑布（`$schema`，`y`/`y2` 为累计起止）。`SUM` 使用加法贡献，每一层子项差值之和等于总差值，并在结果里记录 `closes`。`AVG`/`COUNT`/`MIN`/`MAX` 只做水平对比，不声称闭合，`sun_shapley` 为 null。同时传入 `rate_col` 与 `volume_col` 时，只按路径里的第一个维度做 Laspeyres 恒等式，拆成量效应、率效应和交互项（`structure_effect` 与交互项是同一个交叉项）；后面的维度不进入这一拆分。加法层级的 `orderings_used` 是 1，按调用方给出的维度顺序。`sun_shapley` 另外给出两种因子顺序的平均：量效应 `((p0+p1)/2)·Δq`，率效应 `((q0+q1)/2)·Δp`，两者相加等于差值，那里的 `orderings_used` 是 2。`SUM` 的 `sun_shapley` 对维度排列取平均；加法成员的差值不随顺序变化，所以平均值等于单独聚合，`order_invariant` 为真。最多枚举 4 个维度、24 种顺序。

### 12. SPSS 级数理假设检验算子 (`spss_hypothesis_test`)
* **支持类型**：独立样本 t 检验（含 Levene 方差齐性与 Welch 校正）、配对样本 t 检验（`paired_t_test`，两个数值列）、单因素 ANOVA（含事后 Tukey HSD 与 eta^2）、双因素 ANOVA（`two_way_anova`，需要 `factor_b`，含交互项）、卡方独立性检验（含 Cramér's V）、Mann-Whitney U 检验。`one_way_anova` 与 `two_way_anova` 的 `statistics.variance_decomposition` 带同一套组间/组内分解；显著性判定仍是原来的 F 与效应量门槛。`mann_whitney` 在组数不是 2 时返回错误，不再取前两组。扫描单元格超过 5,000,000 时错误文案为「请先聚合再检验」。`significant` 同时要求 p 值过线，以及效应量过线：|Cohen's d| ≥ 0.2、η² ≥ 0.01、Cramér's V ≥ 0.1、|rank-biserial r| ≥ 0.1。

### 方差分解算子 (`variance_decomposition`)
* **作用**：对一个数值指标按类别维度做总方差分解。组间与组内平方和闭合。`sun_shapley` 是维度排列上的顺序增量平均，最多 4 维、24 种顺序。恰好两个维度且设计平衡时才返回交互项；不平衡时 `ss_interaction` 为 null。多于两个维度时 `interaction` 为 null。交叉分组超过 200000 时要求先聚合。
* **入口**：MCP `variance_decomposition` 把算子字典原样放在 `variance_decomposition` 下，含 `evidence`。REST `POST /api/v1/tools/variance_decomposition` 把同一字典放进 `AnalysisResponse.statistics`。入参是 `session_id`、`dataset_name`、`metric`、`dimensions`、`filters`。

### 13. 多元回归与计量经济学诊断算子 (`spss_regression_analysis`)
* **支持模型**：OLS 多元线性回归（$R^2$、F检验、系数表、VIF 多重共线性诊断、Durbin-Watson 残差自相关检验）、二元 Logistic 回归。自变量超过 40 列，或扫描单元格超过 500 万时，返回「请先聚合再回归」，不把明细拉进进程。

### 14. 自动化洞察挖掘算子 (`detect_automated_insights`)
* **异常点 (Outliers)**：3-Sigma、IQR、孤立森林。REST：`POST /api/v1/insights/outliers`。
* **趋势与拐点 (Trends)**：线性回归斜率显著性检验 + 滑动窗口斜率突变拐点识别。REST：`POST /api/v1/insights/trends`。
* **支配度 (Dominance)**：基尼系数（Gini）与帕累托 80/20 集中度。REST：`POST /api/v1/insights/dominance`。
* MCP 仍是一个 `detect_automated_insights`。三条 REST 用 `AnalysisResponse`：完整结果在 `statistics`，样本行在 `data_preview`（异常点、序列预览、头部贡献者）。

### 15. 内存多维 OLAP 聚合算子 (`memory_olap_aggregation`)
* **作用**：多维切片切块（Slice & Dice）、Rollup 与 Cube 聚合。

### 实测：1000 万行上的 EDA 与相关

2026-10-09，在 Darwin 24.6.0 arm64、Python 3.13.2、DuckDB 1.5.5 上测了一次。会话 `bench_slice` 用 `range(10000000)` 建表 `bench10m`，列是 `id`、`x = i % 1000`、`y = i % 50`、`z = sin(i)`。EDA 和相关各起一个新进程。macOS 的 `ru_maxrss` 单位是字节，峰值包含这张表。建表约 0.21 秒，不在下表的算子耗时里。这是这一次测量，不是性能承诺。

| 算子 | 行数 | 耗时 | 进程峰值 RSS |
| --- | ---: | ---: | ---: |
| `DistributedEDA.profile_table` | 10,000,000 | 0.354 秒（evidence `duration_ms` 354.16） | 592,691,200 字节（565.2 MiB） |
| `run_correlation_analysis`（`x`,`y`,`z`，Pearson） | 10,000,000 | 0.011 秒（evidence `duration_ms` 10.73） | 569,966,592 字节（543.6 MiB） |

`x`、`y`、`z` 的 `quantile_method` 是 `approx_quantile`，四列 `distinct_count_method` 都是 `approx_count_distinct`，`rows_scanned` 为 10000000。相关的 `sample_size` 也是 10000000，`high_correlation_pairs` 为 0。同一张表在 2026-10-08 用精确 `quantile_cont` 时，EDA 是 1.930 秒、峰值 3,229,220,864 字节（3079.6 MiB）。

`DATA_AGENT_RAY_ENABLED=true` 时，行数达到 `DATA_AGENT_RAY_MIN_ROWS`（默认 100 万）的 Pearson 相关会把数值列写成临时 Parquet，按第一列的哈希把行切成多片，合并充分统计量。方差分解用同一开关合并分片分组矩，`backend` 写在 caveat 里。装了 `ray` 就用 Ray 任务，没装就在本进程跑同一份分片函数，结果与单次扫描一致。默认关闭。远程 `DATA_AGENT_RAY_ADDRESS` 要求 worker 能读到这台机器的临时文件。沙箱关掉外部访问后，这条连接不能再写出文件，分片就留在会话连接上，`backend=session`。

`discover_insights` 在配置了 `DATA_AGENT_LLM_BASE_URL` 时，把洞察的 id、标题、严重度和证据字段发给兼容 OpenAI 的接口，只接受一组 id 作为新顺序。接口缺失或失败时按 `severity` 排，并在 `ranking_caveat` 里说明。统计量不由模型重算。

---

## 六、 Trace / 用户行为分析（运行于会话内导入的 trace 表）

> 这些算子不再连独立的采集库；它们对**导入到分析会话的 trace 数据源**（经 `import_traces` 载入）运行，
> 因此与 DB 连接器路径共用同一分析引擎。每个算子入参含 `session_id` 与 `dataset_name`。
> trace 数据源经 `import_traces` 接入（OTLP JSON / span JSON/NDJSON / CSV / Parquet）。

### 16. 转化漏斗算子 (`analyze_conversion_funnel`)
* **入参**：`session_id`, `dataset_name`, `steps`, `date_from?`, `date_to?`
* **作用**：计算多步骤有序转化漏斗、各步骤留存人数、步进流失率与总转化率。`chart_spec` 是 Vega-Lite 柱状图，x 为步骤名，y 为 `user_count`。MCP 把它放在 `funnel` 旁边；REST 与漏斗字段同层。

### 17. 用户流动与桑基图算子 (`analyze_user_flow`)
* **作用**：基于会话内页面访问时序生成转移矩阵。`nodes` / `links` 是桑基拓扑。MCP 在 `user_flow` 旁附 `chart_spec`（ECharts `series.type=sankey`）。REST 把 `nodes`、`links` 与 `chart_spec` 放在同一层。

### 18. 留存队列分析算子 (`analyze_cohort_retention`)
* **作用**：按首次活跃日期划分群组，计算 N 天活跃用户数与留存率。`retention_matrix` 里 `day_N` 是 `{count, rate}`。`chart_spec` 把 rate 展成 Vega-Lite 热力矩形。MCP 放在 `retention` 旁边；REST 与矩阵同层。

### 19. 页面深度分析算子 (`analyze_page_performance`)
* **作用**：计算页面 PV、UV、会话数与平均停留时长，以及全表事件、UV、会话、错误数。结果里没有跳出率字段，也没有图表 spec。

### 20. 链路追踪与操作路径复现 (`inspect_trace_and_replay`)
* **入参**：`session_id`, `dataset_name`, `trace_id?`, `telemetry_session_id?`
* **作用**：从会话内 trace 表构建 OpenTelemetry Span 瀑布流，按遥测 Session 还原用户点击与页面流转时间轴。

---

## 七、 反向 ETL 与数据激活层

### 21. 目标库反向同步算子 (`reverse_sync_destination`)
* **作用**：流式分块将分析结果或 RFM 分群标签反写回外部 PostgreSQL、MySQL、SQLite 或 Parquet/CSV。`chunk_size` 是数据库目的地的 Arrow 批大小，默认 50000。

### 22. 受众分群导出算子 (`export_audience_cohort`)
* **作用**：提取特定受众分群导出为 CSV/JSON 对接业务 CRM。`total_audience_count` 是过滤后的全量，`exported_count` 是本次返回的行数，`truncated` 表示被 `limit` 截断。

### 23. 智能告警推送算子 (`send_operational_webhook_alert`)
* **作用**：`platform=feishu` 发飞书 post 卡片，`dingtalk` 发钉钉 markdown，`slack` 发 `{"text": ...}`。`wecom`、`wechat`、`weixin`、`qywx`、`wxwork`、`wechat_work` 发企业微信 markdown。其他值发通用 JSON：`title`、`message`、`metrics`。推送失败时 `status` 为 `FAILED`，响应里仍会带 `simulated_payload`。

---

## 八、 数据可观测性与质量断言层

### 24. 声明式数据质量断言算子 (`assert_data_quality`)
* **作用**：单遍扫描运行声明式断言，输出健康分。`rules[].type` 只实现四种：`not_null`（`column`）、`unique`（`column`）、`between`（`column`、`min_val`、`max_val`）、`row_count`（`min_rows`、`max_rows`）。其他 type 记为 `unsupported_rule` 且该条失败，会计入健康分分母。

### 25. Schema 漂移检测算子 (`detect_table_schema_drift`)
* **作用**：自动比对字段增减与类型漂移，提供下游熔断保护。

## 通用业务分析报告

新增 `discover_business_report` 与 `generate_business_report` MCP 工具，以及 `/api/v1/reports/discover`、`/api/v1/reports/generate` REST 接口，上传/连接数据后复用同一 session_id。字段识别是候选，用户可改选指标、时间字段、两个业务维度、日/周/月/季/年粒度及明确比较窗口。指标当前只支持可加总 SUM。`filters` 支持最多8项累积精确过滤，用于 Agent 逐层下钻。

通用结果包含时间图数据、维度贡献、异常候选、证据 SQL、核查建议和未执行原因。完整量价成本映射通过正数量、折扣比例、有限数值和利润账式验证后，才启用中点利润桥与金额异常敏感性；缺字段仍返回基础报告。同比仅在窗口内有上一年同期时返回；周同比不计算。成本必须为行总销售成本，折扣必须为减免比例。尚未实现预算差异、本量利或因果识别的全自动流程，不得宣称已运行。详细契约见 `skills/data-analysis-service/references/business_reports.md`。

## 独立指标比较、分解与敏感性工具

新增 REST `POST /api/v1/tools/compare_metric`、`/decompose_change`、`/analyze_sensitivity`，以及同名 MCP 工具。共同指标契约支持 sum、ratio（总分子/总分母）、distinct_count、closing_balance（窗口内每实体末次快照）；共同时间契约规定自然日历粒度、时区、左闭右开窗口、边界对齐、等桶数及调用方声明的完整性水位。严格模式不接受以最大日期代替完整性证据。

分解提供 SUM 维度贡献、比例中点分解及共享利润桥；异常敏感性提供 MAD/IQR/Z-score、基期或合并参考集、分组阈值、按行/实体排除后重算。所有运算只读，由外部 Agent 编排。新工具和通用报告统一 evidence v2（参数、样本、口径、假设、警告、截断、SQL/指纹），其他旧算子保留兼容输出。旧报告仍为 SUM 模式，完整性未知，不能替代严格新契约。

完整请求示例、数学定义、空值/零分母/期末余额规则和 REST/MCP 差异见 [分析契约](../skills/data-analysis-service/references/analytical_contracts.md)。回归覆盖在 `tests/test_analytical_contracts.py`，包含真实 MCP 内存传输、REST 鉴权、接口一致性及数学边界。

订单核查新增 `investigate_orders`（REST POST `/api/v1/tools/investigate_orders`，MCP 参数 `request`）。基于共同时间/指标契约、完整订单映射，提供逐行金额与账式校验、同商品基期折扣围栏、大单规模检查、互斥分类贡献对账和保留参考集的 order_ids 明细下钻。输出 evidence v2；检查通过不代表业务已批准。详见技能 references/analytical_contracts.md 的订单核查契约。

金额深查新增 `reconcile_order_amounts`（REST POST `/api/v1/tools/reconcile_order_amounts`，MCP typed request）。共享指标/时间契约，自动全量选取账式差额订单或显式指定订单；核查重复业务行/行号、候选倍率、折扣含义和映射的逐行税费附加额，并复用利润桥返回原始/精确整单排除分解及各因素差值。没有税费字段时保持未知；输出 evidence v2、截断和不可比分解原因。完整参数见技能 references/analytical_contracts.md。

折扣驱动新增 `analyze_discount_drivers`（REST POST `/api/v1/tools/analyze_discount_drivers`，MCP typed request）。复用共同指标/时间及利润桥口径，整单排除金额异常或明确订单后，按商品及最多4个额外维度拆解同品折扣率变化/标价销售额结构变化。每个维度独立对账同一折扣贡献，保留Top-K遗漏项。focus_dimension/member下钻只筛证据，保留原始分解系数，并返回商品与订单明细。新旧成员缺失率使用明确的分摊约定，非因果结论。详细公式与边界见技能 references/analytical_contracts.md。

折扣订单专项新增 `audit_discount_orders`（REST POST `/api/v1/tools/audit_discount_orders`，MCP typed request）：指定商品、客户/渠道字段及区域filters，复用时间和指标口径，返回当前业务量下超基准折扣额、参考层级/覆盖、目标商品与范围整单毛利、盈亏平衡折扣、可配置核查优先级及稳定基准的订单下钻。基期不同订单数不足则回退或标未知；超基准金额不是同比贡献。完整规则见技能 references/analytical_contracts.md。


### 折扣保本与情景压力工具 `simulate_discount_scenarios`
REST `POST /api/v1/tools/simulate_discount_scenarios` 与同名 MCP 共用 DiscountScenarioRequest、SQL 计算和 v2 evidence；只读，无 Agent 循环。继承 audit_discount_orders 的指标、时间、映射、过滤、排除与三级基期参考。`order_ids` 仅筛明细，不改变总体情景；focus 字段不参与情景计算。

输入 `discount_caps` 减免比例列表（默认 .1/.2/.3/.35），`volume_reductions` 假设销量下降列表（默认 0/.05/.1/.2，始终含零），`variable_cost_share` 成本可变比例（默认 1，业务需确认），均为有限 0–1 值；每列表最多12项。负数量不适用，账式不兼容需修复或排除。

对每行 G=数量×标价，d=实际减免，c=上限，v=降量，C=映射成本，a=可变成本比例：新减免=min(d,c)，情景毛利=G×(1−min(d,c))×(1−v)−C×(1−a×v)。其余商品不变。uplift 相比原公式毛利 G×(1−d)−C；versus_actual 相比实际毛利，另含账式舍入差。保持原公式毛利的容忍降量=固定销量改善/Σ[G×(1−min(d,c))−aC]，分母非正返回 null，超过100%保持原值解释，不能当作需求预测。

订单目标商品统一折扣保本线=1−ΣC/ΣG；范围整单线=1−(ΣC−其他商品实际毛利)/ΣG。零标价分母返回 null，负阈值表示零折扣也亏损。实际执行应向下取整。恢复基期按每行三级参考率执行，参考缺失则整单 restore_uplift/restored_whole_profit 为 null；不是保证收益。成本未含未映射税费/期间费用。

输出 scenario_selection（排除、覆盖、账式差），全量 scenarios、product_scenarios，scenario_orders（保本、恢复、audit 下钻），scenario_lines（参考层级、订单数、原始字段），next_checks；图表区分固定销量与销量压力。商品明细最多2500项、订单/行最多100项，truncation 明示，不影响总体聚合。销量压力是假设而非弹性估计；核查合同、折扣授权、可比基期、成本可变比例与客户流失风险后再评估实施。


#### 多成本销量风险边界（simulate_discount_scenarios 扩展）
REST 路径及 MCP 工具名不变，保留 variable_cost_share 单情景字段兼容旧调用。新增 cost_share_cases（默认 [0,.5,1]，1–5项有限0–1比例）和 robustness_volume_drop（默认 .2）。全量 SQL 按组合及每个商品计算，order_ids 仍只筛订单证据。返回 risk_frontiers、robustness、成本案例及压力参数；图表将维持原毛利与保本明确分开。

令新收入 R=ΣG(1−min(d,cap))，成本 C=Σ成本，原公式毛利 B，成本可变比例 a；降量v下 P(v)=R−C−v(R−aC)。零降量毛利 P0=R−C，斜率 L=R−aC。
- 维持原毛利代数根 (P0−B)/L（L>0）；可行最大降量限制在[0,1]，L<=0时因收紧折扣不降低初始毛利，全区间可保持。
- 零毛利代数根 P0/L（L不为0），原值保留，不将域外根伪装为可实现临界点。
- nonloss_max_drop 仅在P0>=0时定义：L>0为min(1,P0/L)，否则为1。P0<0返回null和initial_loss，不能当作可容忍降量；亏损业务可能在100%停销量后归零，但这不是从盈利转亏的边界。L=0且P0=0为全区间零毛利，代数根null。
- robustness 根据配置压力v，检查全部成本案例以及每个商品。passes_all_cases 要求毛利和较B改善均非负（浮点容差1e-8）；total_only 表示仅组合通过；profit_erodes 表示组合仍盈利但改善被吃掉；loss_risk表示组合有亏损案例。商品×成本退化/亏损计数不可当作不同商品数。

边界是目标商品映射成本口径，非企业净利润。短期固定成本、最低采购承诺、库存与运费应由业务核查。不同上限会有不同需求反应，工具不估计弹性；相同降量压力下数学更优不等于最严格上限应实施。总量稳健性全量计算，风险明细最多2500项且truncation标记。报告使用金色维持毛利线/绿色保本带、统一0–100%横轴和逐商品展开对照。

---

## 九、 Hex 风格 Context Studio 上下文治理、轨迹剧本与上下文可观测性

### P0. Context Studio 四层上下文与认证护栏 (`set_workspace_context_rules` / `register_context_guide` / `endorse_context_asset` / `resolve_session_context`)
* **四层上下文遍历**：
  1. `1_workspace_context`：全局或会话级系统规则、命名规范及默认认证模式开关（`endorsed_only_default`）。
  2. `2_guides`：绑定至工作区、数据表、指标或语义模型的结构化 Markdown 业务口径指南（`ContextGuide`）。
  3. `3_semantic_layer`：受控语义模型与指标定义。
  4. `4_endorsements`：为表、指标、语义模型和指南标记 `endorsed`、`draft`、`deprecated`、`warning` 四档信任等级。
* **Endorsed Mode 护栏**：在 `query_semantic_metric`、`duckdb_sql_sandbox` 及契约分析算子中支持 `endorsed_only=True`（或继承会话规则），自动拦截 `deprecated` 或非 `endorsed` 资产并在非严格模式下注入 `endorsement_warnings`。

### P1. Threads 风格分析轨迹与参数化剧本 (`list_analysis_trail` / `export_analysis_playbook` / `replay_analysis_playbook`)
* **自动轨迹账本**：会话内执行的算子（`compare_metric`、`decompose_change`、`analyze_sensitivity`、`investigate_orders`、`reconcile_order_amounts`、`analyze_discount_drivers`、`audit_discount_orders`、`simulate_discount_scenarios`、`eda_profile`、`memory_olap_aggregation`、`query_semantic_metric`、`duckdb_sql_sandbox` 等）自动记录有序的 `AnalysisStep`。
* **剧本固化与重放**：支持通过 `export_analysis_playbook` 将多步探索固化为 `AnalysisPlaybook`，并通过 `replay_analysis_playbook` 传入 `parameter_overrides`（如替换时间窗口、过滤条件或数据集）全链路确定性重跑。

### P2. dbt Semantic Layer (MetricFlow) YAML 生态互通与连接器扩展 (`import_dbt_semantic_yaml` / `export_dbt_semantic_yaml`)
* **dbt 语义 YAML 导入/导出**：直接解析 dbt `semantic_models`（含 `ref()`/`source()`、`entities`、`dimensions`、`measures`）和 `metrics`（支持 `simple`、`ratio`、`derived`/`custom`、`cumulative`），自动注册为 `SemanticModel` 与 `MetricDefinition`，并支持反向导出标准 YAML。
* **DuckDB / JSON 本地与 Scanner 扩展**：`LocalFileConnector` 与 `duckdb_scanner` 原生支持 `duckdb://`（`.duckdb` 文件只读挂载下推）、`motherduck://` 以及 `.json`/`.ndjson`/`.jsonl` 文件直接内省与 Arrow 抽取。

### P3. Context Observability 上下文健康度自检 (`audit_agent_context_health`)
* **主动预警与评分**：综合评估当前会话的数据资产认证率、语义指标覆盖度、业务指南完备度、裸 SQL（`ungoverned_sql`）调用占比、高空值/非法行丢弃步数及高频警告，输出 0–100 的 `context_health_score`、`proactive_warnings` 和治理改进建议 `recommendations`。
