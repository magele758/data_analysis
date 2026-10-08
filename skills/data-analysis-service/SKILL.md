---
name: data-analysis-service
description: Enterprise Modern Data Stack (MDS) data-processing pipeline engine with two data-source paths that share one analytical engine — (A) DB connectors (PostgreSQL/MySQL/MSSQL/SQLite/File/Excel/CSV) and (B) trace/telemetry import (OTLP JSON, span JSON/NDJSON, CSV/Parquet). Once data lands in an in-memory session table, the full pipeline applies uniformly: clean/transform, dbt-style DAG modeling, Data Catalog & lineage, semantic metric store, EDA profiling, OLAP, SPSS-grade hypothesis testing (t-test/ANOVA/regression), driver attribution, conversion funnels / user-flow Sankey / cohort retention / OpenTelemetry span waterfall & session replay (all on the imported trace table), Great-Expectations quality assertions, schema drift, and Reverse ETL activation (DB/CRM/webhooks). Palantir-style Ontology (Objects, Links, Actions, audit) sits on top. Use when the user asks to import large Excel/CSV datasets or connect a database, import/analyze traces or telemetry, catalog assets, clean data, run DAG pipelines, query standardized metrics, sync data back to DB/CRM/webhooks, run data quality assertions, calculate conversion funnels or trace waterfalls, or perform statistical tests. Note: this service does not collect telemetry itself — collection is an optional demo under examples/telemetry-collector-demo that feeds data in via import_traces.
---

# Enterprise Modern Data Stack & Agentic Ontology Service (Agent Skill)

Provides high-performance, stateless in-memory analytics, large Excel/CSV stream ingestion, Palantir-style business ontology (Objects, Links, Actions), ELT modeling, reverse ETL activation, and SPSS-grade statistical algorithms using DuckDB, Apache Arrow, and OpenTelemetry.

## Quick Start Workflows

### 1. Two Ingestion Paths → One Analytical Session
* **Path A — Database Connectors**: Call `connect_and_load_db` to connect to PostgreSQL/MySQL/MSSQL/SQLite/File with projection & predicate pushdown. `mode="materialize"` (default, ConnectorX) or `mode="scanner"` (DuckDB ATTACH + pushdown for PG/MySQL).
* **Path A — Big Excel / CSV**: Invoke `import_excel_or_csv` with `file_path`, `dataset_name`, optional `sheet_name` to stream-parse million-row files without OOM.
* **Path B — Trace / Telemetry Import**: Invoke `import_traces` with `source` (OTLP JSON, span JSON/NDJSON array, or CSV/Parquet) and `dataset_name` to load trace spans/events as an ordinary session table. It is normalized to a canonical span/event schema so every downstream operator applies.
* All paths land in the same in-memory DuckDB session (`session_id`), so DB data and trace data share one analysis engine.

### 2. Palantir Agentic Ontology Layer
* **Inspect Schema**: Invoke `ontology_list_schema` to discover all business Object Types, Links, and available Actions.
* **Query Entities**: Invoke `ontology_query_objects` to search entity instances and status.
* **Multi-Hop Traversal**: Invoke `ontology_traverse_links` to traverse along relation links across entities (e.g. `Customer -> Orders -> Products`). The result includes `path` and `hop_counts`. MANY_TO_MANY uses the junction table.
* **Execute Actions**: Invoke `ontology_execute_action` to trigger atomic business operations (e.g. `ApplyDiscountAction`, `RerouteOrderAction`). The audit stores before, after, and `statement_hash`. The MCP tool defaults `dry_run=true`. Pass `dry_run=false` to write. `link_path` walks more than one hop. A `writeback_table` on `SQL_MUTATION` stores the edit beside the source table. `REVERSE_ETL_SYNC` calls `DestinationSync` only when `dest_conn_str`, `dest_table_name`, and `source_table` are set.

### 3. Data Catalog & Semantic Layer
* **Catalog Assets**: Auto-registers ingested files/tables into Data Catalog.
* **Semantic Metrics**: Invoke `register_semantic_metric` / `register_semantic_model`, then `query_semantic_metric`. Governed compilation aggregates on the metric's home table and joins only many-to-one, at most two hops. A `RATIO` metric divides the numerator aggregate by the denominator aggregate. The response includes `metric_versions`. `list_semantic_metrics` and `list_session_datasets` read what the session already holds.

### 4. ETL / ELT Transformation & Data Cleansing
* **Data Cleaning**: Invoke `execute_data_cleaning` to deduplicate, fill missing values (mean/median/mode), and clip outliers.
* **DAG Pipeline**: Register SQL models and call `run_dag_pipeline` for transactional dbt-like topological modeling.

### 5. Analytics, Attribution, Mining & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill a metric change. SUM closes as an additive contribution. Pass `rate_col` and `volume_col` for a Laspeyres rate/volume split. `orderings_used` is 1. The result is not a Shapley value.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` (`independent_t_test`, `paired_t_test`, `one_way_anova`, `two_way_anova` with `factor_b`, `chi_square`, `mann_whitney`) and `spss_regression_analysis` for formal inference. `significant` also requires an effect-size floor. More than 40 regressors returns `请先聚合再回归`.
* **Correlation / OLAP Pivot**: `correlation_analysis` (Pearson/Spearman matrix, BH q-values, |r| >= 0.1). Pass `group_col` to surface a Simpson caveat when a group flips the sign. `pivot_table` aggregates rows × columns.
* **Data Mining**: `kmeans_clustering` (auto-k), `rfm_segmentation` (customer value), `timeseries_forecast` (ARIMA(1,1,1) plus a holdout against last-value and, on a calendar, seasonal naive).
* **Trace & Web Analytics (on the imported trace table)**: Use `analyze_conversion_funnel`, `analyze_user_flow`, `analyze_cohort_retention`, `analyze_page_performance`, `inspect_trace_and_replay` — each takes `session_id` + `dataset_name` and runs on the session-resident trace/event table (not a separate store).

### 5b. Insight Copilot (Automated Insight Discovery)
* **Discover Insights**: Invoke `discover_insights` to orchestrate the operators above as *Analysis Actions* (anomaly/correlation/dominance/trend), returning ranked structured insights, an **Insight Graph** (relationships between findings), and a **data-story narrative**. An optional `intent` string lightly biases which actions run. This is the local-deterministic slice of the modern automated-insight paradigm (InsightPilot / DataSage style); deeper NLU intent parsing and multi-agent reasoning are the calling Agent's job.

### 6. Reverse ETL & Operational Activation
* **Destination Sync**: Invoke `reverse_sync_destination` to stream sync analytical results back to PostgreSQL/MySQL/SQLite/Parquet.
* **Audience Export**: Call `export_audience_cohort` to extract high-value or churn-risk users to JSON/CSV for CRM.
* **Operational Webhooks**: Call `send_operational_webhook_alert` to push rich cards to Feishu/DingTalk/Slack.

### 7. Data Observability & Assertions
* **Quality Assertions**: Invoke `assert_data_quality` for declarative single-pass validations (nulls, uniqueness, ranges, row counts).
* **Schema Drift**: Call `detect_table_schema_drift` to compare against baseline schema.

## Notes

- **Session isolation**: Data Catalog, semantic metrics, DAG models, and lineage are scoped per `session_id`. Distinct sessions never see each other's datasets/metrics/models; a DAG run only materializes its own session's models. The ontology catalog is process-global. A session lives in one process; extra workers do not see its tables. Empty `depends_on` is filled from SQL lineage. An explicit list is kept.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 37 MCP tools.
