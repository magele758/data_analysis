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
