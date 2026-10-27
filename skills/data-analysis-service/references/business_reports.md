# General report contract

REST: GET `/api/v1/reports/datasets?session_id=...`, POST `/api/v1/reports/discover`, POST `/api/v1/reports/generate`.
MCP: `discover_business_report` and `generate_business_report` share the same engine.

Generate request: session_id, dataset_name, metric, time_column, grain (day/week/month/quarter/year), dimensions (0–2), base_start, base_end, current_start, current_end. ISO dates satisfy base_start < base_end <= current_start < current_end. End dates excluded. Time span <=10 years, daily <=2000 days. Metric is SUM only; do not submit ratios, balances or distinct user counts without modeling the right measure first.

Optional mapping: product, quantity, price, discount, sales, cost, order; discount_scale=1 or100. Cost is total line COGS; discount is reduction fraction, not retained-price factor. All mandatory profit fields must exist. Quantity must be positive, price/cost nonnegative, values finite, discount within0–1 after conversion. Target metric must equal sales−cost within0.01 per row. Missing/invalid profit mapping returns basic report with explicit skipped reason. Without order mapping sensitivity excludes rows, not entire orders.

Optional filters: mapping of up to8 column names to exact string values, accumulating across turns. Legacy filter_dimension/filter_value accepts a single additional filter. No free SQL filter. Fields validated against schema and quoted; values escaped. Excludes invalid date/nonfinite metric rows and reports counts. Missing time buckets remain null; partial and unequal periods require review. YoY computed only when prior-year matching bucket is within report window; weekly YoY not computed. Dimension rows limited50 (truncation flag); anomalies20; dates/metrics and SQL evidence preserved. Different dimensions cannot be added together.

Response: summary, statistics, series, dimensions, anomalies, profit_bridge, checks, next_steps, skipped, evidence(request, queries, amount-mismatch orders, method). Narrative built deterministically by NarrativeBuilder. No chart_spec protocol change. Frontend charts render this evidence; no LLM computes business totals.

Agent workflow: discover -> confirm mappings/period completeness -> generate -> inspect negative/positive contributions -> generate with cumulative filters -> use existing hypothesis/regression/variance/forecast tools as appropriate -> summarize with evidence and limitations. Do not equate correlation or contribution with causality. Budget, fixed-cost break-even and causal experiments need additional data/design and are not automatically executed.
