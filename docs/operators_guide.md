# 数据分析算子与数学规范指南 (Operators & Mathematical Formulations)

本服务为 Agent 提供了 21 个高度抽象、高信噪比的 IQuery 语义算子，覆盖现代数据栈全生命周期。

---

## 一、 数据接入与沙箱层

### 1. 数据库连接与加载算子 (`connect_and_load_db`)
* **作用**：连接外部 PostgreSQL / MySQL / SQL Server / SQLite / Parquet 文件，按需抽取并加载至当前 Session 内存空间，并自动登记至 Data Catalog。
* **参数**：`conn_str`, `query_or_table`, `dataset_name`, `select_cols`, `filter_sql`, `partition_col`, `num_partitions`。

### 2. DuckDB 安全 SQL 沙箱 (`duckdb_sql_sandbox`)
* **作用**：允许 Agent 直接下发原生 DuckDB SQL 表达复杂分析意图，内置安全只读保护与自动分页限制。

---

## 二、 资产目录与统一指标语义层

### 3. 统一指标语义查询算子 (`query_semantic_metric`)
* **作用**：根据 Semantic Metric Store 中标准化的指标公式与维度定义，自动编译为标准 DuckDB 执行 SQL 并返回结果。

---

## 三、 ETL / ELT 数据清洗与建模层

### 4. 自动化数据清洗算子 (`execute_data_cleaning`)
* **作用**：对指定数据表执行自动去重、空值填充（均值/中位数/众数/常数）、极值缩尾截断（Winsorization）。

### 5. dbt 风格 SQL DAG 建模调度算子 (`run_dag_pipeline`)
* **作用**：基于 Kahn 拓扑排序算法，按模型依赖顺序依次物化 DAG 管道中的所有模型。

---

## 四、 核心数理统计、归因与自动洞察

### 6. EDA 探索性数据画像算子 (`eda_profile`)
* **作用**：全表扫描并秒级输出字段业务语义类型推断、描述性统计、偏度峰度与数据质量综合得分。

### 7. 多维异动下钻与归因算子 (`driver_attribution_analysis`)
* **作用**：针对指标波动，沿维度层级路径逐层下钻，输出 Shapley 贡献度与层级瀑布树。

### 8. SPSS 级数理假设检验算子 (`spss_hypothesis_test`)
* **支持类型**：独立样本 t 检验（含 Levene 方差齐性与 Welch 校正）、单因素 ANOVA 方差分析（含事后 Tukey HSD 与 eta^2）、卡方独立性检验（含 Cramér's V）、Mann-Whitney U 检验。

### 9. 多元回归与计量经济学诊断算子 (`spss_regression_analysis`)
* **支持模型**：OLS 多元线性回归（$R^2$、F检验、系数表、VIF 多重共线性诊断、Durbin-Watson 残差自相关检验）、二元 Logistic 回归。

### 10. 自动化洞察挖掘算子 (`detect_automated_insights`)
* **异常点 (Outliers)**：3-Sigma、IQR、孤立森林。
* **趋势与拐点 (Trends)**：线性回归斜率显著性检验 + 滑动窗口斜率突变拐点识别。
* **支配度 (Dominance)**：基尼系数（Gini）与帕累托 80/20 集中度。

### 11. 内存多维 OLAP 聚合算子 (`memory_olap_aggregation`)
* **作用**：多维切片切块（Slice & Dice）、Rollup 与 Cube 聚合。

---

## 五、 前端遥测与用户行为分析

### 12. 转化漏斗算子 (`analyze_conversion_funnel`)
* **作用**：计算多步骤有序转化漏斗、各步骤留存人数、步进流失率与总转化率。

### 13. 用户流动与桑基图算子 (`analyze_user_flow`)
* **作用**：基于会话内页面访问时序生成 N-Gram 转移矩阵，输出 ECharts 桑基图 (Sankey) 拓扑。

### 14. 留存队列分析算子 (`analyze_cohort_retention`)
* **作用**：按首次活跃日期划分群组，计算 N 天活跃用户数与留存百分比热力图。

### 15. 页面深度分析算子 (`analyze_page_performance`)
* **作用**：计算页面 PV、UV、平均停留时长与跳出分析。

### 16. 链路追踪与操作路径复现 (`inspect_trace_and_replay`)
* **作用**：构建 OpenTelemetry Span 瀑布流，按 Session ID 还原用户点击与页面流转时间轴。

---

## 六、 反向 ETL 与数据激活层

### 17. 目标库反向同步算子 (`reverse_sync_destination`)
* **作用**：将分析结果或 RFM 分群标签反写回外部 PostgreSQL、MySQL、SQLite 或 Parquet/CSV。

### 18. 受众分群导出算子 (`export_audience_cohort`)
* **作用**：提取特定受众分群导出为 CSV/JSON 对接业务 CRM。

### 19. 智能告警推送算子 (`send_operational_webhook_alert`)
* **作用**：向飞书机器人（富文本卡片）、企业微信、钉钉或 Webhook 推送归因告警。

---

## 七、 数据可观测性与质量断言层

### 20. 声明式数据质量断言算子 (`assert_data_quality`)
* **作用**：运行 Great-Expectations 风格的数据质量断言（非空、唯一、数值区间、行数范围），输出健康总评分。

### 21. Schema 漂移检测算子 (`detect_table_schema_drift`)
* **作用**：自动比对字段增减与类型漂移，提供下游熔断保护。
