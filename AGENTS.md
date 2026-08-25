# AGENTS.md - Agent Integration & Maintenance Protocol

本文档定义了 AI Agent 与本数据分析服务的集成规范、架构契约及**代码与 Skill 同步维护钩子（Synchronization Hook Rule）**。

---

## 📌 Agent 核心交互规范 (Interaction Guidelines)

1. **计算与推理职责分离**：
   * **确定性计算下沉**：所有数据聚合、偏度/分位数计算、方差分解、Shapley 归因、t/F 统计检验、ETL 建模必须调用本服务算子，严禁由 LLM 直接做大数心算或经验推测。
   * **高层次编排与业务洞察**：Agent 负责理解用户业务意图，拆解为分析步骤（如：`资产目录发现 -> 数据清洗 -> DAG 建模 -> 归因下钻 -> 假设检验 -> 结果反写/告警激活`），并基于算子返回的结构化统计量和结论组装最终业务汇报。

2. **会话生命周期管理**：
   * 首次操作调用 `connect_and_load_db` 获取 `session_id`。
   * 后续所有分析、建模、逆向同步算子均复用该 `session_id`，利用 DuckDB 内存空间实现秒级零拷贝交互。
   * 会话空闲 30 分钟后自动由后台异步守护线程回收。

---

## 🔄 核心同步钩子规范 (Maintenance Hook & Synchronization Rule)

> [!IMPORTANT]
> **【强制代码与 Skill 联动规则】 (Code-to-Skill Sync Rule)**
> 每当开发者或 Agent 对本代码库进行以下改动时，**必须同步更新相关 Skill 与规范文档**：
>
> 1. **算子新增/修改 (Operator Changes)**：
>    - 若修改或新增 `app/operators/*`、`app/distributed_ops/*`、`app/catalog/*`、`app/transform/*`、`app/retl/*`、`app/observability/*`，必须同步更新：
>      - `app/schemas/requests.py` 与 `app/schemas/responses.py`
>      - `app/mcp_server.py`（更新 Tool Description 与入参）
>      - `skills/data-analysis-service/SKILL.md` 与 `skills/data-analysis-service/references/`
>      - `docs/operators_guide.md`
> 2. **数据源连接器更新 (Connector Changes)**：
>    - 若新增数据源支持（如 ClickHouse, Snowflake, Oracle），必须同步更新：
>      - `app/connectors/factory.py`
>      - `skills/data-analysis-service/SKILL.md` (Description 触发词与支持数据库列表)
> 3. **输出协议与可视化演进 (Protocol Changes)**：
>    - 若调整 Vega-Lite/ECharts 图表 Spec 格式或 NLG 叙述字段，必须同步更新 `app/nlg/narrative_builder.py` 与 `tests/` 测试用例。
> 4. **提交前自检流水线**：
>    - 每次提交前必须在虚拟环境中执行 `.venv/bin/pytest tests/ -v`，确保所有端到端测试 100% 通过。

---

## 🛠️ MCP 接入配置速查

在 Claude Desktop 或 Cursor 中配置：
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
