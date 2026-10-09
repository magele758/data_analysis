# MCP Tools Specification (37 Registered Tools)

Two ingestion paths land data in one session; all analytics run on session tables.
Catalog / metrics / DAG / lineage are scoped per `session_id` (isolated across sessions).

| Tool Name | Category | Key Parameters | Return Value |
| :--- | :--- | :--- | :--- |
| `import_excel_or_csv` | Ingestion (Path A) | `file_path`, `dataset_name`, `sheet_name`, `limit` | `session_id`, `row_count`, `column_count`, `summary` |
| `connect_and_load_db` | Ingestion (Path A) | `conn_str`, `query_or_table`, `dataset_name`, `select_cols`, `filter_sql` | `session_id`, `row_count`, `column_count`, `summary` |
| `import_traces` | Ingestion (Path B) | `source` (OTLP/JSON/NDJSON/CSV/Parquet), `records` (inline spans; wins over `source`), `dataset_name`, `session_id`, `fmt` | `session_id`, `dataset_name`, `row_count`, `columns`, `summary`. REST uses the field name `format`, not `fmt` |
| `ontology_list_schema` | Ontology | None | `status`, `ontology_schema` (objects, links, actions) |
| `ontology_query_objects` | Ontology | `session_id`, `object_type`, `filters`, `properties`, `limit` | `status`, `data` (`object_type`, `primary_key`, `total_instances`, `instances`). REST returns that object directly, without the `data` wrapper |
| `ontology_traverse_links` | Ontology | `session_id`, `source_object_type`, `source_instance_id`, `link_name`, `link_path` | `status`, `traversal` (linked instances, hops, path) |
| `ontology_execute_action` | Ontology | `session_id`, `action_name`, `instance_id`, `parameters`, `dry_run` (default true) | `status`, `action_audit` |
| `eda_profile` | Profiling | `session_id`, `dataset_name` | `summary`, `quality_score`, `total_rows`, `columns` |
| `driver_attribution_analysis` | Attribution | `session_id`, `dataset_name`, `target_metric`, `dimension_path`, `base_filter`, `current_filter`, `rate_col`, `volume_col` | `summary`, `method`, `orderings_used`, `sun_shapley`, `driver_hierarchy`, `chart_spec` |
| `spss_hypothesis_test` | Statistics | `session_id`, `dataset_name`, `test_type`, `dependent_var`, `group_var`, `factor_b`, `alpha` | `summary`, `statistics` |
| `spss_regression_analysis` | Statistics | `session_id`, `dataset_name`, `dependent_var`, `independent_vars`, `model_type` | `summary`, `model_report` |
| `detect_automated_insights` | Insights | `session_id`, `dataset_name`, `metric`, `category_col`, `time_col`, `outlier_method` (`z_score`/`iqr`/`isolation_forest`), `threshold`, `dimension_cols`, `top_k`, `group_col` | `status`, `insights` (`outliers`, `dominance`, `trends`). No separate HTTP route; `OutliersRequest` / `TrendsRequest` / `DominanceRequest` are not mounted |
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
| `run_dag_pipeline` | Transform | `session_id` | `pipeline_execution` (order, results) |
| `reverse_sync_destination` | Reverse ETL | `session_id`, `source_table`, `dest_conn_str`, `dest_table_name` | `sync_result` (synced rows, status) |
| `export_audience_cohort` | Reverse ETL | `session_id`, `source_table`, `filter_sql`, `format_type` | `audience` (count, data) |
| `send_operational_webhook_alert` | Reverse ETL | `webhook_url`, `title`, `message`, `platform` (`feishu` post card, `dingtalk` markdown; `slack` and anything else use one generic JSON body), `extra_metrics` | `alert_result` |
| `assert_data_quality` | Observability | `session_id`, `table`, `rules` | `quality_report` (health score, rules) |
| `detect_table_schema_drift` | Observability | `session_id`, `table`, `baseline_schema` | `drift_report` (add/remove/type changes) |
