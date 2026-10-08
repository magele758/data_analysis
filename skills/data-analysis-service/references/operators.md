# Operators Reference (21 Operators Across 6 MDS Layers)

## 1. Ingestion & Pushdown Connectors
* `connect_and_load_db`: Connects to PostgreSQL, MySQL, SQL Server, SQLite, Parquet/CSV via Rust ConnectorX with predicate & projection pushdown.

## 2. Profiling & Insights
* `eda_profile`: Single-pass sufficient statistics (mean, std, P25, P50, P75, P95, P99, skewness, kurtosis, data quality score).
* `detect_automated_insights`: 3-Sigma/Isolation Forest anomaly detection, temporal slope change points, Gini coefficient & Pareto 80/20.

## 3. OLAP & Root-Cause Attribution
* `memory_olap_aggregation`: Slice & Dice, Rollup, Cube multi-dimensional aggregations in memory.
* `driver_attribution_analysis`: Hierarchical deviation tree. SUM uses a closed additive contribution. `rate_col` + `volume_col` uses a Laspeyres rate/volume split (volume, rate, interaction). Not a Shapley value. Waterfall chart spec is built from the first level.
* `duckdb_sql_sandbox`: Safe read-only DuckDB SQL query execution sandbox.

## 4. SPSS Statistical Inference & Econometrics
* `spss_hypothesis_test`: Independent t-test (Levene equality and Welch correction, Cohen's d), paired t-test on two numeric columns, one-way ANOVA (Tukey HSD and eta-squared), two-way ANOVA with `factor_b` (type II, including the interaction), chi-square (Cramér's V), Mann-Whitney U.
* `spss_regression_analysis`: OLS multi-linear regression (R2, F-test, VIF multicollinearity, Durbin-Watson autocorrelation, Jarque-Bera normality) and Logistic regression.

## 5. Web Telemetry & User Analytics
* `analyze_conversion_funnel`: Multi-step sequential windowed conversion rates and drop-off analysis.
* `analyze_user_flow`: N-Gram page transition matrix with Sankey diagram topology.
* `analyze_cohort_retention`: Cohort user retention heatmap matrix.
* `analyze_page_performance`: PV, UV, average stay dwell seconds, and bounce rate.
* `inspect_trace_and_replay`: OpenTelemetry span waterfall tree and interactive action breadcrumb timeline replay.

## 6. Modern Data Stack (Catalog, Transform, rETL, Quality)
* `query_semantic_metric`: Compile standardized metric formulas into executable SQL. With a semantic model, aggregate on the home table and join many-to-one only. `RATIO` divides two aggregates. The response includes `metric_versions`.
* `register_semantic_metric` / `list_semantic_metrics` / `register_semantic_model` / `list_session_datasets`: Register and list metrics, grains, and session datasets. Source connection strings are redacted.
* `execute_data_cleaning`: Automated deduplication, missing value imputation (mean/median/mode/constant), and outlier clipping.
* `run_dag_pipeline`: Topological DAG model execution using Kahn's algorithm with dependency-ordered materialization.
* `reverse_sync_destination`: Reverse ETL sync of analytical tables/RFM scores back to target databases or files.
* `export_audience_cohort`: Export specific audience segment to JSON/CSV for CRM activation.
* `send_operational_webhook_alert`: Automated operational alert cards sent to Feishu, DingTalk, Slack, or Webhook.
* `assert_data_quality`: Great-Expectations style declarative assertions (nulls, uniqueness, ranges, row counts).
* `detect_table_schema_drift`: Compare table schema against registered baseline to detect added, removed, or altered columns.
