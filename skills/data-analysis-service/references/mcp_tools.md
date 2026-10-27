# MCP Tools Specification (40 Registered Tools)

Two ingestion paths land data in one session; all analytics run on session tables.
Catalog / metrics / DAG / lineage are scoped per `session_id` (isolated across sessions).

| Tool Name | Category | Key Parameters | Return Value |
| :--- | :--- | :--- | :--- |
| `import_excel_or_csv` | Ingestion (Path A) | `file_path`, `dataset_name`, `sheet_name` (omit = first worksheet; unknown name is an error), `limit` | `session_id`, `row_count`, `column_count`, `summary`. Legacy `.xls` is rejected |
| `connect_and_load_db` | Ingestion (Path A) | `conn_str`, `query_or_table`, `dataset_name`, `select_cols`, `filter_sql` | `session_id`, `row_count`, `column_count`, `summary` |
| `import_traces` | Ingestion (Path B) | `source` (OTLP/JSON/NDJSON/CSV/Parquet), `records` (inline spans; wins over `source`), `dataset_name`, `session_id`, `fmt` | `session_id`, `dataset_name`, `row_count`, `columns`, `summary`. REST uses the field name `format`, not `fmt` |
| `ontology_list_schema` | Ontology | None | `status`, `ontology_schema` (objects, links, actions) |
| `ontology_query_objects` | Ontology | `session_id`, `object_type`, `filters`, `properties`, `limit` | `status`, `data` (`object_type`, `primary_key`, `total_instances`, `instances`). REST returns that object directly, without the `data` wrapper |
| `ontology_traverse_links` | Ontology | `session_id`, `source_object_type`, `source_instance_id`, `link_name`, `link_path`, `max_hops` | `status`, `traversal` (`hop_details`, `truncated`, path, hops). REST passes the same `link_path` and `max_hops` |
| `ontology_entity_graph` | Ontology | None | `status`, `entity_graph` (`nodes`, `edges`, `broken_edges`). REST: `GET /api/v1/ontology/entity_graph` |
| `ontology_execute_action` | Ontology | `session_id`, `action_name`, `instance_id`, `parameters`, `dry_run` (default true) | `status`, `action_audit` |
| `eda_profile` | Profiling | `session_id`, `dataset_name` | `summary`, `quality_score`, `total_rows`, `columns`. Measure `skewness` / `kurtosis` / `std` are null when undefined. `quantile_cont` p50 is `quantile_cont` |
| `driver_attribution_analysis` | Attribution | `session_id`, `dataset_name`, `target_metric`, `dimension_path`, `base_filter`, `current_filter`, `rate_col`, `volume_col` | `summary`, `method`, `orderings_used`, `sun_shapley`, `driver_hierarchy`, `chart_spec`, `evidence`. Laspeyres still drills only the first dimension |
| `variance_decomposition` | Statistics | `session_id`, `dataset_name`, `metric`, `dimensions`, `filters` | `variance_decomposition` is the operator dict unchanged, including `evidence`, `factors`, `sequential`, `interaction`, `sun_shapley`. REST `POST /api/v1/tools/variance_decomposition` puts that dict in `statistics` |
| `spss_hypothesis_test` | Statistics | `session_id`, `dataset_name`, `test_type`, `dependent_var`, `group_var`, `factor_b`, `alpha` | `summary`, `statistics`. ANOVA includes `variance_decomposition`. `mann_whitney` requires exactly 2 groups. Over 5,000,000 cells returns 请先聚合再检验 |
| `spss_regression_analysis` | Statistics | `session_id`, `dataset_name`, `dependent_var`, `independent_vars`, `model_type` | `summary`, `model_report` |
| `detect_automated_insights` | Insights | `session_id`, `dataset_name`, `metric`, `category_col`, `time_col`, `outlier_method` (`z_score`/`iqr`/`isolation_forest`), `threshold`, `dimension_cols`, `top_k`, `group_col` | MCP: `status`, `insights` (`outliers`, `dominance`, `trends`). REST splits the same operators: `POST /api/v1/insights/outliers|trends|dominance` returns `AnalysisResponse` (`summary_text`, `statistics`, `data_preview`) |
| `memory_olap_aggregation` | OLAP | `session_id`, `dataset_name`, `dimensions`, `metrics`, `agg_funcs`, `filters`, `rollup`, `cube`, `order_by`, `limit` | `status`, `result` |
| `duckdb_sql_sandbox` | Sandbox | `session_id`, `sql_query`, `limit` | `status`, `result` |
| `correlation_analysis` | Analysis | `session_id`, `dataset_name`, `columns`, `method`, `group_col` | `correlation` (matrix, high_correlation_pairs, evidence; Simpson caveat when `group_col` flips the sign) |
| `pivot_table` | Analysis | `session_id`, `dataset_name`, `rows`, `columns`, `values`, `agg_func` | `pivot` (records, schema) |
| `kmeans_clustering` | Mining | `session_id`, `dataset_name`, `feature_cols`, `n_clusters`, `auto_k_range` | `clustering` (optimal_k, silhouette) |
| `rfm_segmentation` | Mining | `session_id`, `dataset_name`, `user_col`, `date_col`, `amount_col` | `rfm` (segments) |
| `timeseries_forecast` | Mining | `session_id`, `dataset_name`, `time_col`, `value_col`, `horizon`, `model_type` | `forecast` (forecasts, holdout vs naive and seasonal naive, calendar gaps), `chart_spec` (Vega-Lite line + 95% errorband) |
| `discover_insights` | Insight Copilot | `session_id`, `dataset_name`, `intent`, `target_metric`, `category_col`, `time_col` | `insight_report` (insights, insight_graph, narrative, ranking_method, ranking_caveat) |
| `analyze_conversion_funnel` | Trace Analytics | `session_id`, `dataset_name`, `steps`, `date_from`, `date_to` | MCP: `funnel` (`total_steps`, `initial_users`, `overall_conversion_rate`, `steps`) plus sibling `chart_spec` (Vega-Lite bar). REST returns the funnel fields at the top level plus `chart_spec` |
| `analyze_user_flow` | Trace Analytics | `session_id`, `dataset_name`, `limit_paths` | MCP: `user_flow` (`nodes`, `links`, `total_transitions`) plus sibling `chart_spec` (ECharts sankey). REST returns those fields at the top level plus `chart_spec` |
| `analyze_cohort_retention` | Trace Analytics | `session_id`, `dataset_name`, `days` | MCP: `retention` (`cohorts`, `days_analyzed`, `retention_matrix`) plus sibling `chart_spec` (Vega-Lite heatmap). REST returns those fields at the top level plus `chart_spec` |
| `analyze_page_performance` | Trace Analytics | `session_id`, `dataset_name`, `limit` | MCP wraps `page_metrics`. Fields are `summary` (events, UV, sessions, errors) and `pages` (PV, UV, sessions, avg dwell). No bounce rate and no chart spec |
| `inspect_trace_and_replay` | Trace Analytics | `session_id`, `dataset_name`, `trace_id`, `telemetry_session_id` | `waterfall` spans, `replay` timeline |
| `query_semantic_metric` | Catalog | `session_id`, `metric_names`, `dimensions`, `filters` | `compiled_sql`, `result`, `governed`, `metric_versions` |
| `register_semantic_metric` | Catalog | `session_id`, `name`, `table_name`, `formula`, `dimensions`, `numerator_metric`, `denominator_metric` | `metric` |
| `list_semantic_metrics` | Catalog | `session_id` | `metrics` |
| `register_semantic_model` | Catalog | `session_id`, `name`, `table_name`, `grain`, `columns`, `entities` | `model` |
| `list_session_datasets` | Catalog | `session_id` | `datasets` (source credentials redacted) |
| `execute_data_cleaning` | Transform | `session_id`, `source_table`, `target_table`, `dedup_keys`, `fillna_rules` | `cleaning_result` (rows, removed duplicates) |
| `create_wide_table` | Transform | `session_id`, `target_name`, `fact_table`, `dimension_joins` | `wide_table` (`wide_table_name`, `row_count`, `columns`). REST: `POST /api/v1/transform/wide` |
| `run_dag_pipeline` | Transform | `session_id` | `pipeline_execution` (order, results). Same-stage models run sequentially |
| `reverse_sync_destination` | Reverse ETL | `session_id`, `source_table`, `dest_conn_str`, `dest_table_name`, `chunk_size` | `sync_result` (synced rows, status) |
| `export_audience_cohort` | Reverse ETL | `session_id`, `source_table`, `filter_sql`, `format_type` | `audience` (`total_audience_count`, `exported_count`, `truncated`, data) |
| `send_operational_webhook_alert` | Reverse ETL | `webhook_url`, `title`, `message`, `platform` (`feishu`, `dingtalk`, `slack`, `wecom`/`wechat`/`weixin`/`qywx`/`wxwork`/`wechat_work`), `extra_metrics` | `alert_result`. `FAILED` still includes `simulated_payload` |
| `assert_data_quality` | Observability | `session_id`, `table`, `rules` | `quality_report` (health score, rules) |
| `detect_table_schema_drift` | Observability | `session_id`, `table`, `baseline_schema` | `drift_report` (add/remove/type changes) |

## General report tools

- `discover_business_report(session_id, dataset_name, grain="month")`: schema, candidate mapping, suggested periods.
- `generate_business_report(session_id, dataset_name, config)`: config follows BusinessReportRequest; returns JSON BusinessReportResponse. Supports cumulative `filters` for iterative drilldown. See [business_reports.md](business_reports.md).

## Typed analytical tools

Added `compare_metric(request)`, `decompose_change(request)`, and `analyze_sensitivity(request)`. `request` is a structured object (not a JSON string); tool schemas expose MetricCompareRequest, DecompositionRequest and SensitivityRequest. They return `status, summary, result, evidence` objects, with evidence schema version 2.0. HTTP equivalents are POST `/api/v1/tools/<tool_name>` with the unwrapped request body. See [input examples, defaults, method limits and compatibility](analytical_contracts.md).

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
