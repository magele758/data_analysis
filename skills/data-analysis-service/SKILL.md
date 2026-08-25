---
name: data-analysis-service
description: Enterprise Modern Data Stack (MDS) & Palantir-Style Agentic Ontology data intelligence engine. Supports Business Objects (Customer, Order, Device), Entity Links & Graph Traversal, Closed-Loop Actions & Audit Trails, Data Catalog & Lineage, Semantic Metric Store, ETL/ELT data cleaning & DAG modeling, Reverse ETL data activation, Data Quality assertions, OpenTelemetry web analytics (funnels, user flow Sankey, cohort retention, trace replay), EDA profiling, multi-dimensional drill-down attribution, and SPSS-grade hypothesis testing (t-test, ANOVA, regression). Use when the user asks to query business entities, traverse entity relation graphs, execute business actions, catalog assets, clean data, run DAG pipelines, query standardized metrics, sync data back to DB/CRM/webhooks, run data quality assertions, calculate conversion funnels, or perform statistical tests.
---

# Enterprise Modern Data Stack & Agentic Ontology Service (Agent Skill)

Provides high-performance, stateless in-memory analytics, Palantir-style business ontology (Objects, Links, Actions), ELT modeling, reverse ETL activation, and SPSS-grade statistical algorithms using DuckDB, Apache Arrow, and OpenTelemetry.

## Quick Start Workflows

### 1. Palantir Agentic Ontology Layer
* **Inspect Schema**: Invoke `ontology_list_schema` to discover all business Object Types, Links, and available Actions.
* **Query Entities**: Invoke `ontology_query_objects` to search entity instances and status.
* **Multi-Hop Traversal**: Invoke `ontology_traverse_links` to traverse along relation links across entities (e.g. `Customer -> Orders -> Products`).
* **Execute Actions**: Invoke `ontology_execute_action` to trigger atomic business operations (e.g. `ApplyDiscountAction`, `RerouteOrderAction`) with full audit trails.

### 2. Data Catalog & Semantic Layer
* **Catalog Assets**: Call `connect_and_load_db` to auto-register assets into Data Catalog.
* **Semantic Metrics**: Invoke `query_semantic_metric` to compute standardized metrics compiled to DuckDB SQL.

### 3. ETL / ELT Transformation & Data Cleansing
* **Data Cleaning**: Invoke `execute_data_cleaning` to deduplicate, fill missing values (mean/median/mode), and clip outliers.
* **DAG Pipeline**: Register SQL models and call `run_dag_pipeline` for dbt-like topological modeling.

### 4. Analytics, Attribution & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill down root-cause drivers with Shapley contributions.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` and `spss_regression_analysis` for formal inference.
* **Web & Trace Analytics**: Use `analyze_conversion_funnel`, `analyze_user_flow`, `analyze_cohort_retention`, `inspect_trace_and_replay`.

### 5. Reverse ETL & Operational Activation
* **Destination Sync**: Invoke `reverse_sync_destination` to sync analytical results back to PostgreSQL/MySQL/SQLite/Parquet.
* **Audience Export**: Call `export_audience_cohort` to extract high-value or churn-risk users to JSON/CSV for CRM.
* **Operational Webhooks**: Call `send_operational_webhook_alert` to push rich cards to Feishu/DingTalk/Slack.

### 6. Data Observability & Assertions
* **Quality Assertions**: Invoke `assert_data_quality` for declarative validations (nulls, uniqueness, ranges, row counts).
* **Schema Drift**: Call `detect_table_schema_drift` to compare against baseline schema.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options for all 25 operators.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 25 MCP tools.
