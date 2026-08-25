---
name: data-analysis-service
description: Enterprise Modern Data Stack (MDS) & Palantir-Style Agentic Ontology data intelligence engine. Supports loading large Excel (.xlsx, .xls) and CSV files, Business Objects (Customer, Order, Device), Entity Links & Graph Traversal, Closed-Loop Actions & Audit Trails, Data Catalog & Lineage, Semantic Metric Store, ETL/ELT data cleaning & DAG modeling, Reverse ETL data activation, Data Quality assertions, OpenTelemetry web analytics (funnels, user flow Sankey, cohort retention, trace replay), EDA profiling, multi-dimensional drill-down attribution, and SPSS-grade hypothesis testing (t-test, ANOVA, regression). Use when the user asks to import large Excel/CSV datasets, query business entities, traverse entity relation graphs, execute business actions, catalog assets, clean data, run DAG pipelines, query standardized metrics, sync data back to DB/CRM/webhooks, run data quality assertions, calculate conversion funnels, or perform statistical tests.
---

# Enterprise Modern Data Stack & Agentic Ontology Service (Agent Skill)

Provides high-performance, stateless in-memory analytics, large Excel/CSV stream ingestion, Palantir-style business ontology (Objects, Links, Actions), ELT modeling, reverse ETL activation, and SPSS-grade statistical algorithms using DuckDB, Apache Arrow, and OpenTelemetry.

## Quick Start Workflows

### 1. Big File & Multi-Source Data Ingestion
* **Import Big Excel / CSV**: Invoke `import_excel_or_csv` with `file_path`, `dataset_name`, and optional `sheet_name` to stream parse million-row files into memory without OOM.
* **Database Connectors**: Call `connect_and_load_db` to connect to PostgreSQL/MySQL/MSSQL/SQLite with predicate pushdown.

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

### 5. Analytics, Attribution & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill down root-cause drivers with Shapley contributions.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` and `spss_regression_analysis` for formal inference.
* **Web & Trace Analytics**: Use `analyze_conversion_funnel`, `analyze_user_flow`, `analyze_cohort_retention`, `inspect_trace_and_replay`.

### 6. Reverse ETL & Operational Activation
* **Destination Sync**: Invoke `reverse_sync_destination` to stream sync analytical results back to PostgreSQL/MySQL/SQLite/Parquet.
* **Audience Export**: Call `export_audience_cohort` to extract high-value or churn-risk users to JSON/CSV for CRM.
* **Operational Webhooks**: Call `send_operational_webhook_alert` to push rich cards to Feishu/DingTalk/Slack.

### 7. Data Observability & Assertions
* **Quality Assertions**: Invoke `assert_data_quality` for declarative single-pass validations (nulls, uniqueness, ranges, row counts).
* **Schema Drift**: Call `detect_table_schema_drift` to compare against baseline schema.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options for all 26 operators.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 26 MCP tools.
