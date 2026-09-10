# 部署指南 (Deployment)

本服务是一个 **FastAPI + DuckDB 内存分析引擎**（外加可选的 FastMCP server）。运行时无状态、内存密集、单进程即可对外服务；会话数据在内存中、按 TTL 回收。

## 部署要求

| 项 | 要求 |
|---|---|
| 运行时 | Python 3.10+（镜像用 `python:3.13-slim`） |
| 对外端口 | **8000**（HTTP / REST / 看板 / OpenAPI） |
| 进程 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| CPU/内存 | 内存密集（DuckDB 全内存 + Arrow）。建议起步 **2 vCPU / 4–8 GiB**，按数据规模上调；`DATA_AGENT_DUCKDB_MEMORY_LIMIT` 控制单实例内存上限 |
| 持久化 | 默认无需持久卷（会话内存态、TTL 回收）。如需保留全局 Catalog/上传文件，可挂载卷到 `/app/data` |
| 依赖服务 | 无强制外部依赖（不需要 Ray/Postgres 才能启动）；Reverse ETL / trace 导入按需连外部库 |
| MCP | `python -m app.mcp_server`，默认 **stdio** 传输（不占网络端口）；仅在启用 SSE 时才需要 `MCP_SSE_PORT` |

### 关键环境变量（前缀 `DATA_AGENT_`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `DATA_AGENT_API_KEYS` | 逗号分隔的 API Key；**生产必须设置** | 空 |
| `DATA_AGENT_REQUIRE_AUTH` | 是否强制鉴权。未配 Key 且为 `true` 时**拒绝启动**；本地开发可设 `false` | `true` |
| `DATA_AGENT_CORS_ALLOW_ORIGINS` | 允许的前端源（逗号分隔，禁止 `*`+credentials） | `http://localhost:8000,http://127.0.0.1:8000` |
| `DATA_AGENT_DUCKDB_MEMORY_LIMIT` | DuckDB 内存上限 | `16GB` |
| `DATA_AGENT_SESSION_TTL_SECONDS` | 会话空闲回收时间 | `1800` |
| `DATA_AGENT_LOG_LEVEL` | 日志级别 | `INFO` |

> 会话是**每实例内存态**：多副本部署时需**会话亲和**（helm 已配置 `DATA_SESSION_ID` cookie 亲和），否则同一 `session_id` 的后续请求可能落到没有该会话的副本。

### 健康检查

- `GET /health` → `{"status":"ok"}`（公开，不受鉴权影响；镜像内置 `HEALTHCHECK`）。

## 用 Docker 运行

```bash
docker run -d --name data-analysis -p 8000:8000 \
  -e DATA_AGENT_API_KEYS="prod-key-1,prod-key-2" \
  ghcr.io/magele758/data_analysis:latest

# 本地快速体验（关闭鉴权，仅限可信环境）
docker run --rm -p 8000:8000 -e DATA_AGENT_REQUIRE_AUTH=false \
  ghcr.io/magele758/data_analysis:latest
# 看板: http://localhost:8000/dashboard  · OpenAPI: /docs
```

## 镜像构建与发布（tag 打镜像）

两个 workflow：

- **`.github/workflows/ci.yml`** — push `main` 时跑测试并构建 `latest`（多架构，QEMU）。
- **`.github/workflows/release-image.yml`（tag 驱动，推荐用于发版）** — 推送 **语义化 tag** 时构建多架构镜像并按语义版本发布到 GHCR：

```bash
git tag v1.2.3
git push origin v1.2.3
# → ghcr.io/magele758/data_analysis:1.2.3, :1.2, :1, :latest
```

要点（参考 ppeng-agent-core / hyper-vibekanban 的 tag→GHCR 模式）：
- 触发：`push` 语义 tag `v*.*.*`，或手动 `workflow_dispatch`（指定 ref + 自定义 tag，如 `edge`）。
- 多架构：**amd64（ubuntu-latest）+ arm64（ubuntu-24.04-arm）原生构建**，各自 push-by-digest，再用 `buildx imagetools` 合并成一个 manifest —— 避免 QEMU 慢速模拟。
- 认证：内置 `GITHUB_TOKEN`，无需额外 secret。
- 版本 tag 由 `docker/metadata-action` 从 git tag 自动派生（`1.2.3` / `1.2` / `1` / `latest`）。

## Kubernetes / Helm

`helm/` 提供 Service + Ingress（含会话亲和）。设置 `image.repository=ghcr.io/magele758/data_analysis`、`image.tag=<版本>`，并通过 Secret 注入 `DATA_AGENT_API_KEYS`。

> Ray 已非必需（分布式算子现为单机内存 DuckDB 实现），`rayCluster.enabled` 默认关闭。
