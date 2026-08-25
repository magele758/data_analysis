---
name: data-analysis-service
description: Enterprise Modern Data Stack (MDS) data intelligence engine. Supports Data Catalog metadata & lineage, Semantic Metric Store, ETL/ELT data cleaning & DAG modeling, Reverse ETL data activation (DB sync, audience export, webhook alerts), Data Quality assertions, OpenTelemetry telemetry & web analytics (funnels, user flow Sankey, cohort retention, trace replay), EDA profiling, multi-dimensional drill-down attribution, automated insights, and SPSS-grade hypothesis testing (t-test, ANOVA, regression). Use when the user asks to catalog data assets, clean data, run DAG pipelines, query standardized metrics, sync data back to DB/CRM/webhooks, run data quality assertions, calculate conversion funnels, trace user journeys, or perform statistical tests.
---

# Modern Data Stack (MDS) Data Analysis & Intelligence Service (Agent Skill)

Provides high-performance, stateless in-memory and distributed analytics, data cataloging, ELT modeling, reverse ETL activation, and SPSS-grade statistical algorithms using DuckDB, Apache Arrow, and OpenTelemetry.

## Quick Start Workflows

### 1. Data Catalog & Semantic Layer
* **Catalog Assets**: Call `connect_and_load_db` to auto-register assets into Data Catalog.
* **Semantic Metrics**: Invoke `query_semantic_metric` to compute standardized metrics compiled to DuckDB SQL.

### 2. ETL / ELT Transformation & Data Cleansing
* **Data Cleaning**: Invoke `execute_data_cleaning` to deduplicate, fill missing values (mean/median/mode), and clip outliers.
* **DAG Pipeline**: Register SQL models and call `run_dag_pipeline` for dbt-like topological modeling.

### 3. Analytics, Attribution & SPSS Testing
* **EDA Profiling**: Invoke `eda_profile` for semantic types, distribution stats, and data quality scores.
* **Driver Attribution**: Invoke `driver_attribution_analysis` to drill down root-cause drivers with Shapley contributions.
* **SPSS Testing & Regression**: Use `spss_hypothesis_test` and `spss_regression_analysis` for formal inference.
* **Web & Trace Analytics**: Use `analyze_conversion_funnel`, `analyze_user_flow`, `analyze_cohort_retention`, `inspect_trace_and_replay`.

### 4. Reverse ETL & Operational Activation
* **Destination Sync**: Invoke `reverse_sync_destination` to sync analytical results back to PostgreSQL/MySQL/SQLite/Parquet.
* **Audience Export**: Call `export_audience_cohort` to extract high-value or churn-risk users to JSON/CSV for CRM.
* **Operational Webhooks**: Call `send_operational_webhook_alert` to push rich cards to Feishu/DingTalk/Slack.

### 5. Data Observability & Assertions
* **Quality Assertions**: Invoke `assert_data_quality` for declarative validations (nulls, uniqueness, ranges, row counts).
* **Schema Drift**: Call `detect_table_schema_drift` to compare against baseline schema.

## Reference Documentation

- [Operators Guide](references/operators.md) - Mathematical formulations and detailed parameter options for all 21 operators.
- [MCP Tools Reference](references/mcp_tools.md) - Exact schema and payload definitions for all 21 MCP tools.
