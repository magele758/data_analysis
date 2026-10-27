---
name: data-analysis-service
description: Enterprise Modern Data Stack (MDS) data-processing pipeline engine with two data-source paths that share one analytical engine — (A) DB connectors (PostgreSQL/MySQL/MSSQL/SQLite/File/Excel/CSV) and (B) trace/telemetry import (OTLP JSON, span JSON/NDJSON, CSV/Parquet). Once data lands in an in-memory session table, the full pipeline applies uniformly: clean/transform, dbt-style DAG modeling, Data Catalog & lineage, semantic metric store, EDA profiling, OLAP, SPSS-grade hypothesis testing (t-test/ANOVA/regression), driver attribution, conversion funnels / user-flow Sankey / cohort retention / OpenTelemetry span waterfall & session replay (all on the imported trace table), Great-Expectations quality assertions, schema drift, and Reverse ETL activation (DB/CRM/webhooks). Palantir-style Ontology (Objects, Links, Actions, audit) sits on top. Use when the user asks to import large Excel/CSV datasets or connect a database, import/analyze traces or telemetry, catalog assets, clean data, run DAG pipelines, query standardized metrics, sync data back to DB/CRM/webhooks, run data quality assertions, calculate conversion funnels or trace waterfalls, or perform statistical tests. Note: this service does not collect telemetry itself — collection is an optional demo under examples/telemetry-collector-demo that feeds data in via import_traces.
---

# Enterprise Modern Data Stack & Agentic Ontology Service (Agent Skill)

Provides high-performance, stateless in-memory analytics, large Excel/CSV stream ingestion, Palantir-style business ontology (Objects, Links, Actions), ELT modeling, reverse ETL activation, and SPSS-grade statistical algorithms using DuckDB, Apache Arrow, and OpenTelemetry.

## Quick Start Workflows

### 1. Two Ingestion Paths → One Analytical Session
* **Path A — Database Connectors**: Call `connect_and_load_db` to connect to PostgreSQL/MySQL/MSSQL/SQLite/File with projection & predicate pushdown. `mode="materialize"` (default, ConnectorX) or `mode="scanner"` (DuckDB ATTACH + pushdown for PG/MySQL).
* **Path A — Big Excel / CSV**: Invoke `import_excel_or_csv` with `file_path` and `dataset_name`. Omitting `sheet_name` reads the first worksheet. A sheet name that is not in the workbook is an error. Legacy `.xls` is rejected.
* **Path B — Trace / Telemetry Import**: Invoke `import_traces` with `source` (OTLP JSON, span JSON/NDJSON array, or CSV/Parquet) and `dataset_name` to load trace spans/events as an ordinary session table. It is normalized to a canonical span/event schema so every downstream operator applies.
* All paths land in the same in-memory DuckDB session (`session_id`), so DB data and trace data share one analysis engine.

### 2. Palantir Agentic Ontology Layer
* **Inspect Schema**: Invoke `ontology_list_schema` to discover all business Object Types, Links, and available Actions.
* **Query Entities**: Invoke `ontology_query_objects` to search entity instances and status.
* **Multi-Hop Traversal**: Invoke `ontology_traverse_links` to traverse along relation links across entities (e.g. `Customer -> Orders -> Products`). Pass `link_path` and `max_hops`. The result includes `path`, `hop_counts`, `hop_details`, and `truncated`. Object queries include `matched_count` for the filtered total. MANY_TO_MANY uses the junction table. `ontology_entity_graph` returns nodes, edges, and broken_edges.
* **Execute Actions**: Invoke `ontology_execute_action` to trigger atomic business operations (e.g. `ApplyDiscountAction`, `RerouteOrderAction`). The audit stores before, after, and `statement_hash`. A webhook result of `FAILED` stays `FAILED` even when `simulated_payload` is present. The MCP tool defaults `dry_run=true`. Pass `dry_run=false` to write. `link_path` walks more than one hop. A `writeback_table` on `SQL_MUTATION` stores the edit beside the source table. `REVERSE_ETL_SYNC` calls `DestinationSync` only when `dest_conn_str`, `dest_table_name`, and `source_table` are set.

### 3. Data Catalog & Semantic Layer
* **Catalog Assets**: Auto-registers ingested files/tables into Data Catalog.
* **Semantic Metrics**: Invoke `register_semantic_metric` / `register_semantic_model`, then `query_semantic_metric`. Governed compilation aggregates on the metric's home table and joins only many-to-one, at most two hops. A `RATIO` metric divides the numerator aggregate by the denominator aggregate. The response includes `metric_versions`. `list_semantic_metrics` and `list_session_datasets` read what the session already holds.

### 4. ETL / ELT Transformation & Data Cleansing
* **Data Cleaning**: Invoke `execute_data_cleaning` to deduplicate, fill missing values (mean/median/mode), and clip outliers.
* **DAG Pipeline**: Register SQL models and call `run_dag_pipeline` for transactional dbt-like topological modeling. Models in one stage run sequentially on the session connection. `create_wide_table` joins a fact table to dimensions and returns `columns`.

### 5. Analytics, Attribution, Mining & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill a metric change. SUM closes as an additive contribution. Pass `rate_col` and `volume_col` for a Laspeyres rate/volume split on the first dimension only (`orderings_used` 1) plus `sun_shapley`, which averages the two factor orders (`orderings_used` 2). Later dimensions are not drilled on that path. SUM also returns `sun_shapley` over dimension permutations; a pure SUM member diff is order-invariant. Other aggregations leave `sun_shapley` null.
* **Variance decomposition**: Invoke `variance_decomposition` with `metric` and `dimensions`. The operator dict, including `evidence`, is returned as-is. REST `POST /api/v1/tools/variance_decomposition` puts it in `statistics`.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` (`independent_t_test`, `paired_t_test`, `one_way_anova`, `two_way_anova` with `factor_b`, `chi_square`, `mann_whitney`) and `spss_regression_analysis` for formal inference. `one_way_anova` and `two_way_anova` include `variance_decomposition`. `mann_whitney` requires exactly 2 groups. `significant` also requires an effect-size floor. More than 40 regressors returns `请先聚合再回归`. More than 5,000,000 scanned cells returns `请先聚合再检验`.
* **EDA moments**: `eda_profile` leaves `skewness`, `kurtosis`, and `std` null when the moment is undefined. A `quantile_cont` profile uses `quantile_cont` for p50.
* **Correlation / OLAP Pivot**: `correlation_analysis` (Pearson/Spearman matrix, BH q-values, |r| >= 0.1). Pass `group_col` to surface a Simpson caveat when a group flips the sign. With `DATA_AGENT_RAY_ENABLED=true`, a large Pearson scan merges hash partitions of the first numeric column. Ray is used when the package is installed and the connection can still spill a parquet file. If spill is blocked, the same slices stay on the session connection and the caveat says `backend=session`. `pivot_table` aggregates rows × columns.
* **Data Mining**: `kmeans_clustering` (auto-k), `rfm_segmentation` (customer value), `timeseries_forecast` (ARIMA(1,1,1) plus a holdout against last-value and, on a calendar, seasonal naive). The forecast payload includes a Vega-Lite `chart_spec`.
* **Trace & Web Analytics (on the imported trace table)**: Use `analyze_conversion_funnel`, `analyze_user_flow`, `analyze_cohort_retention`, `analyze_page_performance`, `inspect_trace_and_replay` — each takes `session_id` + `dataset_name` and runs on the session-resident trace/event table (not a separate store). Funnel, retention, and user flow also return `chart_spec` (Vega-Lite bar, Vega-Lite heatmap, ECharts sankey). Page metrics do not include a bounce rate or a chart.

### 5b. Insight Copilot (Automated Insight Discovery)
* **Discover Insights**: Invoke `discover_insights` to orchestrate the operators above as *Analysis Actions* (anomaly/correlation/dominance/trend), returning ranked structured insights, an **Insight Graph** (relationships between findings), and a **data-story narrative**. An optional `intent` string lightly biases which actions run. `ranking_method` is `severity` unless `DATA_AGENT_LLM_BASE_URL` is set, in which case the endpoint reorders ids from titles, severity, and evidence fields and falls back to severity on failure. Deeper NLU and multi-agent reasoning stay with the calling Agent.
* **Single actions over HTTP**: `POST /api/v1/insights/outliers`, `/trends`, and `/dominance` call the same operators as `detect_automated_insights`. Each returns `AnalysisResponse` with the operator payload in `statistics` and the sample rows in `data_preview`.

### 6. Reverse ETL & Operational Activation
* **Destination Sync**: Invoke `reverse_sync_destination` to stream sync analytical results back to PostgreSQL/MySQL/SQLite/Parquet. `chunk_size` sets the Arrow batch size.
* **Audience Export**: Call `export_audience_cohort` to extract high-value or churn-risk users to JSON/CSV for CRM. `total_audience_count` is the filtered total, `exported_count` is the page, and `truncated` says whether `limit` cut the page short.
* **Operational Webhooks**: Call `send_operational_webhook_alert`. `feishu` sends a post card, `dingtalk` sends markdown, and `slack` sends `{"text": ...}`. `wecom`, `wechat`, `weixin`, `qywx`, `wxwork`, and `wechat_work` send WeCom markdown. Other platforms send generic JSON. A failed send is `FAILED` and still includes `simulated_payload`.

### 7. Data Observability & Assertions
* **Quality Assertions**: Invoke `assert_data_quality` for declarative single-pass validations (nulls, uniqueness, ranges, row counts).
* **Schema Drift**: Call `detect_table_schema_drift` to compare against baseline schema.

## Notes

- **Session isolation**: Data Catalog, semantic metrics, DAG models, and lineage are scoped per `session_id`. Distinct sessions never see each other's datasets/metrics/models; a DAG run only materializes its own session's models. The ontology catalog is process-global. A session lives in one process; extra workers do not see its tables. Empty `depends_on` is filled from SQL lineage. An explicit list is kept.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 40 MCP tools.

### 5c. General evidence reports for uploaded data

`discover_business_report(session_id, dataset_name, grain)` suggests field mappings and comparison windows from the actual schema. Suggestions require business interpretation. `generate_business_report(session_id, dataset_name, config)` runs the same report engine as `/api/v1/reports/generate`: selected SUM metric, date grain, explicit end-exclusive base/current windows, up to two separate dimension contributions, temporal comparisons, Z-score candidates, evidence SQL and next checks. Optional validated product/quantity/price/discount/sales/cost/order mapping enables a hierarchical midpoint profit bridge and amount-mismatch sensitivity. Use `filters` (up to 8 exact dimension values) for cumulative Agent drilldowns. Missing mappings do not prevent the basic report; invalid quantity/discount or profit accounting identity disables the profit bridge with an explicit reason. This does not implement causal inference, budget analysis or a general autonomous Agent loop. See `references/business_reports.md`.

### 5d. Strict composable analysis tools (REST + MCP)

Prefer `compare_metric`, `decompose_change`, and `analyze_sensitivity` for external Agent composition. They share explicit metric contracts (sum, ratio of sums, distinct count, within-window closing balance), calendar/timezone contracts, end-exclusive windows and caller-declared completeness watermarks. Decomposition supports additive dimensions, ratio midpoint and the shared profit bridge; sensitivity supports MAD/IQR/Z-score with row/entity exclusion and before/after recomputation. All return evidence v2; invalid/undefined results are not silently converted to zero. MCP accepts a typed `request` object; REST accepts its body directly. No Agent loop is added. Legacy report APIs remain compatible. Read [Analytical contracts](references/analytical_contracts.md) before choosing parameters or interpreting results.

### 5e. Order investigation

Use `investigate_orders(request)` after sensitivity to distinguish accounting mismatches, same-product baseline discount outliers, and large orders passing checks. Requires SUM profit and complete order-level mapping. Category contributions reconcile across all scoped orders; overlapping flags are not double-counted. `order_ids` drills evidence without refitting references. Never describe a statistical outlier as fraud or a checks-passed order as verified normal. See [contracts](references/analytical_contracts.md).

### 5f. Amount forensics and exact-order exclusion

Use `reconcile_order_amounts(request)` to check duplicate features, candidate amount multipliers, alternative discount definitions and explicitly mapped line adjustments, then compare original versus selected-order-excluded profit bridges. Empty order_ids selects every accounting mismatch before truncation. Missing tax fields stay unknown; passing duplicate checks is not proof of no upstream duplication. Inspect effect_changes to distinguish amount residuals from removed real business. See [contracts](references/analytical_contracts.md).

### 5g. Discount drivers after exclusion

Use `analyze_discount_drivers(request)` to allocate the shared profit bridge discount effect across product and supplied customer/region/channel dimensions. It separates within-product member discount-rate changes from list-amount share changes, reconciles every view, and returns stable-reference focus drilldowns to product cells and orders. Do not add dimensions together or call residual business verified normal. Read [mathematical and exclusion contracts](references/analytical_contracts.md).

### 5h. Discount order audit and priorities

Use `audit_discount_orders(request)` to target products within region/business filters, identify customer/channel/order discount burden and distinguish target-product loss from all-product scoped order loss. Reference discounts use explicit baseline cohort fallback and distinct-order thresholds. Configurable priorities and break-even discount evidence are review guidance, not fraud or causal claims. `focus_order_id`, `focus_customer`, and `focus_channel` retain the original comparison/reference context. See [contracts](references/analytical_contracts.md).


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
