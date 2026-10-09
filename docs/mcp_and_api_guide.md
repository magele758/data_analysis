# MCP 与 RESTful API 接入与编排指南 (Integration Guide)

## 1. 挂载至 Claude Desktop / Cursor (MCP 模式)

### 配置文件路径：
* **macOS (Claude Desktop)**: `~/Library/Application Support/Claude/claude_desktop_config.json`
* **macOS (Cursor)**: `~/.cursor/mcp.json`

### 配置内容：
```json
{
  "mcpServers": {
    "data-analysis-service": {
      "command": "/path/to/data-analysis-service/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "/path/to/data-analysis-service"
      }
    }
  }
}
```

---

## 2. 挂载至 Dify / LangChain / AutoGen (RESTful API 模式)

### 启动服务：
```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### OpenAPI 文档地址：
* Swagger UI: `http://localhost:8000/docs`
* OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## 3. 输出契约（与当前实现一致）

HTTP 分析端点使用 `AnalysisResponse`：`summary_text`、`statistics`、`chart_spec`、`data_preview`。MCP 把同一段叙述放在 `summary`，统计结果用各自的键（`statistics`、`model_report`、`forecast`、`funnel` 等）。

已挂上的 `chart_spec`：

| 结果 | 规格 |
| :--- | :--- |
| 归因 | Vega-Lite v5 瀑布，`$schema` 指向 v5，`y`/`y2` 为累计起止 |
| 预测 | Vega-Lite 折线，预测段带 95% `errorband`。数据来自 `historical_preview` 与 `forecasts` |
| 漏斗 | Vega-Lite 柱，步骤名 × `user_count`。REST 与漏斗字段同层；MCP 在 `funnel` 旁 |
| 留存 | Vega-Lite 热力，把 `day_N.rate` 展成行。REST 与矩阵同层；MCP 在 `retention` 旁 |
| 用户流 | ECharts sankey（`series.type=sankey`）。REST 与 `nodes`/`links` 同层；MCP 在 `user_flow` 旁 |

回归结果没有观测点行，所以不会附上 `build_scatter_regression_chart`。页面指标没有跳出率，也没有图表 spec。

叙述：EDA 会带上 `type_inference_sample_rows` 以及列上的 `distinct_count_method` / `quantile_method`。归因会带上 `method`，并在 `sun_shapley` 为空时直接说空。假设检验按返回的 `significant` 叙述，不把「不显著」写成 `p >= 0.05`。Logistic 用 Pseudo R² 与 LLR p，不用 OLS 的 R² / VIF 模板。

`POST /api/v1/insights/outliers`、`/trends`、`/dominance` 调用与 MCP `detect_automated_insights` 相同的算子，响应是 `AnalysisResponse`（`statistics` 为完整结果，`data_preview` 为异常点、序列预览或头部贡献者）。MCP 仍把三项包在 `insights` 里。

`POST /api/v1/tools/variance_decomposition` 与 MCP `variance_decomposition` 调用 `run_variance_decomposition`。HTTP 把算子字典放在 `statistics`。MCP 把同一字典放在 `variance_decomposition`，含 `evidence`。归因 MCP 另外返回 `evidence`；Laspeyres 仍只拆第一个维度。

质量规则只实现 `not_null`、`unique`、`between`、`row_count`。其余 type 记为失败的 `unsupported_rule`。

本体查询：MCP 是 `{status, data}`，`instances` 在 `data` 里。REST 直接返回引擎对象。动作的 `dry_run`：MCP 默认 true，REST 默认 false。
