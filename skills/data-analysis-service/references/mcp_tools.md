# MCP Tools Specification (33 Registered Tools)

Two ingestion paths land data in one session; all analytics run on session tables.
Catalog / metrics / DAG / lineage are scoped per `session_id` (isolated across sessions).

| Tool Name | Category | Key Parameters | Return Value |
| :--- | :--- | :--- | :--- |
| `import_excel_or_csv` | Ingestion (Path A) | `file_path`, `dataset_name`, `sheet_name`, `limit` | `session_id`, `row_count`, `column_count`, `summary` |
| `connect_and_load_db` | Ingestion (Path A) | `conn_str`, `query_or_table`, `dataset_name`, `select_cols`, `filter_sql` | `session_id`, `row_count`, `column_count`, `summary` |
| `import_traces` | Ingestion (Path B) | `source` (OTLP/JSON/NDJSON/CSV/Parquet), `dataset_name`, `session_id`, `fmt` | `session_id`, `dataset_name`, `row_count`, `columns`, `summary` |
| `ontology_list_schema` | Ontology | None | `status`, `ontology_schema` (objects, links, actions) |
| `ontology_query_objects` | Ontology | `session_id`, `object_type`, `filters`, `properties`, `limit` | `status`, `instances` |
| `ontology_traverse_links` | Ontology | `session_id`, `source_object_type`, `source_instance_id`, `link_name` | `status`, `traversal` (linked instances) |
| `ontology_execute_action` | Ontology | `session_id`, `action_name`, `instance_id`, `parameters`, `dry_run` | `status`, `action_audit` |
| `eda_profile` | Profiling | `session_id`, `dataset_name` | `summary`, `quality_score`, `total_rows`, `columns` |
| `driver_attribution_analysis` | Attribution | `session_id`, `dataset_name`, `target_metric`, `dimension_path`, `base_filter`, `current_filter` | `summary`, `driver_hierarchy`, `chart_spec` |
| `spss_hypothesis_test` | Statistics | `session_id`, `dataset_name`, `test_type`, `dependent_var`, `group_var`, `alpha` | `summary`, `statistics` |
| `spss_regression_analysis` | Statistics | `session_id`, `dataset_name`, `dependent_var`, `independent_vars`, `model_type` | `summary`, `model_report` |
| `detect_automated_insights` | Insights | `session_id`, `dataset_name`, `metric`, `category_col`, `time_col` | `status`, `insights` |
| `memory_olap_aggregation` | OLAP | `session_id`, `dataset_name`, `dimensions`, `metrics`, `agg_funcs`, `rollup` | `status`, `result` |
| `duckdb_sql_sandbox` | Sandbox | `session_id`, `sql_query`, `limit` | `status`, `result` |
| `correlation_analysis` | Analysis | `session_id`, `dataset_name`, `columns`, `method` | `correlation` (matrix, high_correlation_pairs) |
| `pivot_table` | Analysis | `session_id`, `dataset_name`, `rows`, `columns`, `values`, `agg_func` | `pivot` (records, schema) |
| `kmeans_clustering` | Mining | `session_id`, `dataset_name`, `feature_cols`, `n_clusters`, `auto_k_range` | `clustering` (optimal_k, silhouette) |
| `rfm_segmentation` | Mining | `session_id`, `dataset_name`, `user_col`, `date_col`, `amount_col` | `rfm` (segments) |
| `timeseries_forecast` | Mining | `session_id`, `dataset_name`, `time_col`, `value_col`, `horizon`, `model_type` | `forecast` |
| `discover_insights` | Insight Copilot | `session_id`, `dataset_name`, `intent`, `target_metric`, `category_col`, `time_col` | `insight_report` (insights, insight_graph, narrative) |
| `analyze_conversion_funnel` | Trace Analytics | `session_id`, `dataset_name`, `steps`, `date_from`, `date_to` | `total_steps`, `initial_users`, `overall_conversion_rate` |
| `analyze_user_flow` | Trace Analytics | `session_id`, `dataset_name`, `limit_paths` | `nodes`, `links`, `total_transitions` |
| `analyze_cohort_retention` | Trace Analytics | `session_id`, `dataset_name`, `days` | `cohorts`, `days_analyzed`, `retention_matrix` |
| `analyze_page_performance` | Trace Analytics | `session_id`, `dataset_name`, `limit` | `summary`, `pages` (PV, UV, dwell time) |
| `inspect_trace_and_replay` | Trace Analytics | `session_id`, `dataset_name`, `trace_id`, `telemetry_session_id` | `waterfall` spans, `replay` timeline |
| `query_semantic_metric` | Catalog | `session_id`, `metric_names`, `dimensions`, `filters` | `compiled_sql`, `result` |
| `execute_data_cleaning` | Transform | `session_id`, `source_table`, `target_table`, `dedup_keys`, `fillna_rules` | `cleaning_result` (rows, removed duplicates) |
| `run_dag_pipeline` | Transform | `session_id` | `pipeline_execution` (order, results) |
| `reverse_sync_destination` | Reverse ETL | `session_id`, `source_table`, `dest_conn_str`, `dest_table_name` | `sync_result` (synced rows, status) |
| `export_audience_cohort` | Reverse ETL | `session_id`, `source_table`, `filter_sql`, `format_type` | `audience` (count, data) |
| `send_operational_webhook_alert` | Reverse ETL | `webhook_url`, `title`, `message`, `platform`, `extra_metrics` | `alert_result` |
| `assert_data_quality` | Observability | `session_id`, `table`, `rules` | `quality_report` (health score, rules) |
| `detect_table_schema_drift` | Observability | `session_id`, `table`, `baseline_schema` | `drift_report` (add/remove/type changes) |
