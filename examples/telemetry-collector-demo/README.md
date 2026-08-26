# 遥测采集示例 (Telemetry Collector Demo)

> ⚠️ 这是一个**可选的独立示例**，不属于主数据分析服务。

主服务的定位是「**DB 连接器 + trace 两条路的数据分析服务**」，核心是**现代数据栈数据处理管道**。
trace 在主服务里是一个**导入式数据源**（通过 `import_traces` / `POST /api/v1/import/traces` 接入），
主服务**不自己做埋点采集**。

本示例演示 trace 这条路的**上游来源**：如何采集浏览器/OpenTelemetry 遥测，并把采集到的数据
交给主服务的管道去分析。

## 组成

| 文件 | 作用 |
|---|---|
| `browser-tracker/` | 前端埋点采集 SDK（PV/UV/点击/Web Vitals/JS 异常），W3C Trace Context |
| `collector.py` | 采集端点 `POST /api/v1/collect/events`、实时流 `GET /api/v1/collect/realtime` |
| `event_store.py` | 采集落地（DuckDB `events`/`traces_spans` 表 + 实时环形缓冲） |
| `ring_buffer.py` | 线程安全实时环形缓冲 |
| `demo_server.py` | 独立 FastAPI 应用，挂载采集端点 + SDK 静态页 + `/export` 导出桥 |

## 运行

```bash
cd examples/telemetry-collector-demo
pip install fastapi uvicorn duckdb pyarrow
uvicorn demo_server:app --port 8100
```

- 打开 `http://localhost:8100/sdk/` 生成埋点事件
- `GET http://localhost:8100/export` 导出 `import_traces` 兼容的 `{"events": [...]}` 载荷

## 把采集数据喂给主服务管道

```bash
# 1) 导出采集到的遥测
curl -s http://localhost:8100/export > telemetry.json

# 2) 在主服务里作为“trace 数据源”导入到一个分析会话
#    （MCP 工具 import_traces，或 REST /api/v1/import/traces）
#    之后即可对它跑 EDA / OLAP / SPSS / 漏斗 / trace 瀑布 / 质量断言 / Reverse ETL —— 与 DB 连接器路径同一套算子
```

这样，**采集只是数据来源**；真正的「现代数据栈数据处理」发生在主服务的统一分析引擎里。
