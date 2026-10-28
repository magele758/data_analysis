# Operators Reference (22 Operators Across 6 MDS Layers)

## 1. Ingestion & Pushdown Connectors
* `connect_and_load_db`: Connects to PostgreSQL, MySQL, SQL Server, SQLite, Parquet/CSV via Rust ConnectorX with predicate & projection pushdown.

## 2. Profiling & Insights
* `eda_profile`: Single-pass sufficient statistics (mean, std, P25, P50, P75, P95, P99, skewness, kurtosis, data quality score). Tables over 100,000 rows use `approx_count_distinct` and `approx_quantile`. Undefined skewness, kurtosis, and std stay null. When `quantile_method` is `quantile_cont`, p50 is `quantile_cont`.
* `detect_automated_insights`: 3-Sigma/Isolation Forest anomaly detection, temporal slope change points, Gini coefficient & Pareto 80/20. REST exposes the same three operators at `POST /api/v1/insights/outliers`, `/trends`, and `/dominance`.

## 3. OLAP & Root-Cause Attribution
* `memory_olap_aggregation`: Slice & Dice, Rollup, Cube multi-dimensional aggregations in memory.
* `driver_attribution_analysis`: Hierarchical deviation tree. SUM uses a closed additive contribution and a `sun_shapley` average over dimension permutations. Other aggregations set `sun_shapley` to null. `rate_col` + `volume_col` keeps the Laspeyres split on the first dimension only and adds a two-ordering Sun-Shapley of rate and volume. Waterfall chart spec is built from the first level.
* `duckdb_sql_sandbox`: Safe read-only DuckDB SQL query execution sandbox.

## 4. SPSS Statistical Inference & Econometrics
* `variance_decomposition`: Law of total variance across categorical dimensions. Between and within sums of squares close. `sun_shapley` averages order-sensitive increments (at most 4 dimensions). Interaction is present only for a balanced two-dimension design.
* `spss_hypothesis_test`: Independent t-test (Levene equality and Welch correction, Cohen's d), paired t-test on two numeric columns, one-way ANOVA (Tukey HSD, eta-squared, and `variance_decomposition`), two-way ANOVA with `factor_b` (type II, including the interaction, plus `variance_decomposition`), chi-square (Cramér's V), Mann-Whitney U (exactly 2 groups). More than 5,000,000 scanned cells returns 请先聚合再检验.
* `spss_regression_analysis`: OLS multi-linear regression (R2, F-test, VIF multicollinearity, Durbin-Watson autocorrelation, Jarque-Bera normality) and Logistic regression.

## 5. Web Telemetry & User Analytics
* `analyze_conversion_funnel`: Multi-step sequential windowed conversion rates and drop-off analysis.
* `analyze_user_flow`: N-Gram page transition matrix with Sankey diagram topology.
* `analyze_cohort_retention`: Cohort user retention heatmap matrix.
* `analyze_page_performance`: PV, UV, sessions, and average dwell seconds. There is no bounce-rate field.
* `inspect_trace_and_replay`: OpenTelemetry span waterfall tree and interactive action breadcrumb timeline replay.

## 6. Modern Data Stack (Catalog, Transform, rETL, Quality)
* `query_semantic_metric`: Compile standardized metric formulas into executable SQL. With a semantic model, aggregate on the home table and join many-to-one only. `RATIO` divides two aggregates. The response includes `metric_versions`.
* `register_semantic_metric` / `list_semantic_metrics` / `register_semantic_model` / `list_session_datasets`: Register and list metrics, grains, and session datasets. Source connection strings are redacted.
* `execute_data_cleaning`: Automated deduplication, missing value imputation (mean/median/mode/constant), and outlier clipping.
* `run_dag_pipeline`: Topological DAG model execution using Kahn's algorithm with dependency-ordered materialization.
* `reverse_sync_destination`: Reverse ETL sync of analytical tables/RFM scores back to target databases or files.
* `export_audience_cohort`: Export a segment to JSON/CSV. `total_audience_count` is the filtered total, `exported_count` is the page, and `truncated` records the limit.
* `create_wide_table`: Join a fact table to dimension tables. The result includes `columns`.
* `send_operational_webhook_alert`: Feishu post card, DingTalk markdown, Slack `text`, and WeCom markdown for `wecom`, `wechat`, `weixin`, `qywx`, `wxwork`, `wechat_work`. Failure is `FAILED` even when `simulated_payload` is present.
* `assert_data_quality`: Great-Expectations style declarative assertions (nulls, uniqueness, ranges, row counts).
* `detect_table_schema_drift`: Compare table schema against registered baseline to detect added, removed, or altered columns.

## General business report

The `app.operators.business_report` orchestrator computes selected SUM metric changes, calendar series, separate dimensional contributions, Z-score candidates, and validated optional midpoint profit decomposition using the session SQL sandbox. See [business_reports.md](business_reports.md) for exact mappings, period boundaries, skips and cumulative filters. No external actions or data deletion occur.

## Strict composable analysis

`compare_metric`, `decompose_change`, `analyze_sensitivity` share typed metric/time contracts and evidence v2. Use them for reusable comparisons, additive/ratio/profit decomposition, and MAD/IQR/Z-score sensitivity. See [complete contracts and formulas](analytical_contracts.md); distinct counts and closing balances cannot use additive dimension decomposition. The profit implementation is shared with the general report.

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

## 7. Hex-Style Context Studio, Playbook Replay & Context Health
* `set_workspace_context_rules` / `register_context_guide` / `endorse_context_asset` / `resolve_session_context`: Manage the 4-layer Context Traversal Hierarchy (Workspace Rules, Markdown Business Guides, Semantic Layer, Endorsements) and enforce `endorsed_only` guardrails across SQL and semantic queries.
* `import_dbt_semantic_yaml` / `export_dbt_semantic_yaml`: Import and export dbt Semantic Layer (MetricFlow) / OSI YAML (`semantic_models`, `measures`, and `simple`/`ratio`/`derived`/`cumulative` `metrics`).
* `list_analysis_trail` / `export_analysis_playbook` / `replay_analysis_playbook`: Automatic session-scoped `AnalysisStep` ledger and deterministic parameter-overridable Playbook replay.
* `audit_agent_context_health`: Proactive observability auditor returning `context_health_score` (0–100), ungoverned SQL ratio, unendorsed table queries, warning frequency, and governance recommendations.
