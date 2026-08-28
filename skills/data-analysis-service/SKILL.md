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
* **Multi-Hop Traversal**: Invoke `ontology_traverse_links` to traverse along relation links across entities (e.g. `Customer -> Orders -> Products`).
* **Execute Actions**: Invoke `ontology_execute_action` to trigger atomic business operations (e.g. `ApplyDiscountAction`, `RerouteOrderAction`) with full audit trails.

### 3. Data Catalog & Semantic Layer
* **Catalog Assets**: Auto-registers ingested files/tables into Data Catalog.
* **Semantic Metrics**: Invoke `query_semantic_metric` to compute standardized metrics compiled to DuckDB SQL.

### 4. ETL / ELT Transformation & Data Cleansing
* **Data Cleaning**: Invoke `execute_data_cleaning` to deduplicate, fill missing values (mean/median/mode), and clip outliers.
* **DAG Pipeline**: Register SQL models and call `run_dag_pipeline` for transactional dbt-like topological modeling.

### 5. Analytics, Attribution, Mining & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill down root-cause drivers with Shapley contributions.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` and `spss_regression_analysis` for formal inference.
* **Correlation / OLAP Pivot**: `correlation_analysis` (Pearson/Spearman matrix + strong pairs), `pivot_table` (rows × columns aggregation).
* **Data Mining**: `kmeans_clustering` (auto-k), `rfm_segmentation` (customer value), `timeseries_forecast` (ARIMA-family).
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

- **Session isolation**: Data Catalog, semantic metrics, DAG models, and lineage are scoped per `session_id`. Distinct sessions never see each other's datasets/metrics/models; a DAG run only materializes its own session's models.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 33 MCP tools.
