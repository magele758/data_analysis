# 可组合分析工具：指标、时间与证据契约

本服务负责确定性计算。业务含义确认、假设选择、循环下钻和行动决策由外部 Agent 负责；本次没有新增 Agent 运行时。三个工具复用上传/数据库接入返回的 `session_id`，只读会话数据。

| MCP 工具 | REST POST | 用途 |
|---|---|---|
| compare_metric | /api/v1/tools/compare_metric | 指标比较和日历序列 |
| decompose_change | /api/v1/tools/decompose_change | 维度、比例或利润变化分解 |
| analyze_sensitivity | /api/v1/tools/analyze_sensitivity | 异常识别与排除前后重算 |

REST 请求直接传对象；MCP 参数为 `{"request": 请求对象}`。三者共享请求契约和实现，输出均为 `status, summary, result, evidence`。REST 沿用服务认证；字段校验失败为422，数据/业务校验失败为400；MCP 返回工具错误。字段名称必须来自实际 schema。

## 共同请求

```json
{
  "session_id": "YOUR_SESSION_ID",
  "dataset_name": "sales",
  "metric": {"kind": "sum", "column": "profit", "unit": "CNY"},
  "time": {
    "column": "order_date", "input_mode": "date", "timezone": "Asia/Shanghai",
    "grain": "month", "base_start": "2025-01-01", "base_end": "2025-02-01",
    "current_start": "2025-02-01", "current_end": "2025-03-01",
    "completeness": "strict", "complete_until": "2025-03-01"
  },
  "filters": {}, "invalid_rows": "reject"
}
```

保存为 request.json 后调用（API key 按部署配置提供）：

```sh
curl -X POST http://127.0.0.1:8765/api/v1/tools/compare_metric \
  -H 'Content-Type: application/json' --data-binary @request.json
```

`filters` 最多8个字段的精确字符串匹配，可累计条件逐层下钻。新契约禁止未声明字段，避免拼写错误被静默忽略。

### 指标口径

- `sum`: 指定 `column`，可加总金额/数量。
- `ratio`: 指定 `numerator`、`denominator`，先分别求和再相除，绝不平均行比例；总分母为零返回 null。
- `distinct_count`: 指定 `column`，在整个窗口独立去重，不能把分组/逐日去重数相加当总数。
- `closing_balance`: 指定 `column` 和 `entity_keys`，每个窗口/时间桶取各实体最后观测再合计。同实体同时间重复快照拒绝；没有跨窗口结转，也不推定实体全集完整。日日期模式无法区分同日多次快照，应提供有时区的时间戳。

`unit` 由调用方声明，不进行币种换算或业务字段猜测。相对变化为 delta / abs(base) × 100；基期零则 null。时间桶缺记录为 null，不冒充零活动。默认拒绝非法时间和非有限指标，显式 `invalid_rows=exclude` 才排除并记录数量；无法归期的非法日期按整个过滤后数据源计数。

### 时间口径

所有窗口左闭右开，基期结束不晚于当期开始。支持日、周、月、季、年，周一为周首，使用自然日历。默认边界对齐且桶数相等；月份天数可不同，不做日均归一化。主动关闭 `require_aligned` 或 `require_equal_buckets` 才允许部分桶或不等长窗口，并输出警告。

`date` 模式按业务日期读取，不应用时区换算；`aware_timestamp` 要求原生带时区类型或带 Z/±hh:mm 后缀的字符串，先转指定 IANA 时区再归期，拒绝无时区字符串。

默认 `completeness=strict` 要求 `complete_until >= current_end`。水位也是结束日期不包含，属于调用方对数据完整性的声明，不是服务独立证明；最大观测日期不代表数据完整。无法确认时显式用 `warn`，输出未知/不完整警告。跨度最多十年，日粒度最多2000天。尚不支持财务日历、自动同比对齐、滚动窗口或缺失快照结转。

## 分解

在共同请求上增加：

- `mode=dimension, dimension=region, top_k=50`：只允许 sum，输出成员贡献及全量/展示/遗漏贡献和对账误差；Top-K 不改变总量。
- `mode=ratio`：只允许 ratio。令比率为 A/B，对 A 与 1/B 做对称中点分解：ΔA×平均(1/B)，平均A×Δ(1/B)。总分母为零时拒绝分解。它是账式分解，不是独立干预的因果效应。
- `mode=profit`：sum 指标须为利润；`mapping` 必须包含 `product, quantity, price, discount, sales, cost` 字段名，`order` 可选，`discount_scale` 为1或100。数量必须正，价格/成本非负，折扣为减免比例，成本为行总成本，利润约等于销售额减成本（容差0.01源单位）。采用共享层次中点利润桥，返回销量、商品结构、售价、折扣、单位成本及金额/账式残差；另给金额不一致订单排除后的复核桥。映射不成立时明确拒绝，不编造原因。

## 异常敏感性

在共同请求上增加 `anomaly_column`，以及可选参数：

- `method`: mad（默认阈值3.5）、iqr（围栏系数1.5）、zscore（阈值3）；可显式传正数 `threshold`。
- `reference`: base 默认仅以基期拟合阈值；pooled 显式合并两期。`group_by` 可按业务群组拟合。
- `removal`: row 默认排除异常行；entity 搭配 `entity_column` 排除已标记实体在当前筛选和两个窗口内的所有行，不删除源数据。
- `limit`: 1–500，控制候选明细，默认20；总计不受截断影响。

返回原始/排除后指标、变化差、异常/排除/保留/无法评分数量及候选证据。参考样本不足、无对应参考组或 MAD/标准差为零时保留并标记无法评分，不解释成没有异常。排除后无记录的期间返回 null。候选 query_row_id 是本次查询的临时序号，不是持久主键。敏感性不证明异常是错误订单，也不证明利润下降由异常导致。

## 证据 v2 与兼容

`evidence.schema_version="2.0"` 包括 operator、method、session_id、dataset_name、parameters、population、metric_semantics、time_semantics、assumptions、warnings、truncation、sql、query_sha256、duration_ms、causal_claim=false。SHA256 标识执行 SQL，不是数据内容哈希。会话过期/数据变化后，仅有 SQL 无法保证复现原结果；多查询工具期间调用方应保持数据稳定。

三项独立工具统一使用该输出；通用 generate_business_report 也接入 v2，并保留原 request/queries/orders 等兼容字段。旧报告仍为 SUM 契约，不强制新水位；其时间完整性标为未知。其他历史算子维持原输出，未宣称全部迁移 v2。前端图表 Spec 未更改；result 是可供外部报告生成器使用的数值数据。

建议外部编排：确认字段/单位和水位 → compare_metric → decompose_change → 累计 filters 下钻 → analyze_sensitivity → 按问题调用已有统计检验。所有步骤复用同一 session、metric、time 和 filters，保留每步 evidence；核查建议不得写成已验证原因。

## 订单核查 investigate_orders

REST `POST /api/v1/tools/investigate_orders`，MCP `investigate_orders(request)`。继承 SensitivityRequest 的指标/时间/过滤及异常方法，另需完整 mapping（包括 order）。指标为 SUM 利润，数量必须正、成本非负、折扣归一化后0–1。缺失/非法映射拒绝，不能把退货误当正常销售核查。

`amount_tolerance=0.01` 为源单位逐行容差，分别检查销售额−数量×标价×(1−折扣)及利润−(销售额−成本)，保留绝对差合计防止正负抵消。折扣默认同商品基期 Q3+1.5×IQR，至少 `min_reference_rows=5`；可显式 `discount_threshold`（归一化0–1）。大单阈值是基期订单销售额 Q3+1.5×IQR，样本不足不贴正常标签。基期本身参与阈值拟合，不是留一法。候选标记复现指定 MAD/IQR/Z-score 的行规则再扩展至订单；无法评分不等于正常。

以订单×期间聚合，类别互斥优先级：amount_mismatch → discount_outlier → insufficient_evidence → large_order_checks_passed → other_checks_passed。金额与折扣双重命中仍返回两个标记，汇总只记一次。各类当期利润减基期利润之和等于总变化；这是观察贡献，不是纠错后反事实。金额差额也不自动等于损失。正常大单只能表述为“大单检查通过”，仍需合同、审批、交付和回款凭证。

返回 `categories, reconciliation, orders, line_evidence, next_checks` 及 evidence v2。默认明细20条，limit最大500；报告默认50条。`orders[].drilldown` 为可再次调用本工具的完整请求。`order_ids` 最多100个，仅过滤明细，不改变基期参考与全量贡献；逐行证据最多500行并明确截断。同订单跨两个期间分别展示，核查范围只限当前过滤及窗口。实体复用或订单主键范围应由调用方确认。

折扣超基准金额以同商品基期折扣中位数计算：Σ数量×标价×max(实际减免比例−中位数,0)，按类别分别输出基期/当期金额；参考不足时保留未定义。这是保持当期数量与价格不变的诊断参照，不是估计已证实损失，也不能与类别利润贡献相加。分类构成迁移可能使折扣异常类利润贡献为正，不能据此认定折扣改善利润。

## 金额深查 reconcile_order_amounts

REST `POST /api/v1/tools/reconcile_order_amounts`；MCP `reconcile_order_amounts(request)`。继承 MetricCompareRequest（SUM 利润），需完整 mapping（order/product/quantity/price/discount/sales/cost）。默认 order_ids=[] 自动选择当前范围内任意一行金额或利润账式差额超 amount_tolerance（默认0.01源单位）的全部订单，不受明细 limit（默认100、最大500）截断影响。显式 order_ids（最多100）可核查任意订单；排除时移除该订单在两个窗口及筛选范围内全部行。无写入或自动纠错。

可选 line_id 检查同订单内重复行号；同业务字段重复按订单、日期、商品、数量、标价、折扣、销售额、成本和利润分组。重复是线索，合法拆单也可能相同；未重复不能证明上游没有重复。输出记录的销售额、q×p×(1−d)、观察倍率及匹配的候选 multipliers（默认0.01/0.1/10/100/1000）。按源金额绝对容差匹配；预期金额为零则倍率未定义。倍率仅代表数值相符，不认定是单位错误。

另外返回不计折扣及把 d 解释为保留比例时的金额差额。adjustments 可映射最多8个不重复的逐行有符号税费/运费等附加金额列；需由业务确认这些列应加到公式金额上，订单总额不得复制到每行。没有映射时 tax_fee_status=unknown_missing_fields；缺失值或非有限值不按零处理，记录覆盖行数。服务不猜税率。

输出 selection、orders、line_evidence、profit_bridges、effect_changes、skipped 和 v2 evidence。profit_bridges 复用层次中点法，分别返回原始与 excluding_selected；因素差额用 SQL 计算。利润账式不成立时分解明确跳过，核查依据仍返回。排除导致期间空缺则不可比，不能视为零。整单排除会一并去除正常业务，不能把变化差额都认定为错误金额或将剩余业务自动标为正常。

`exclusion_summary` 仅在两期排除后可比且两套分解成功时返回：delta_difference（排除后总变化−原始总变化）、residual_difference（金额残差贡献差）、other_factor_difference（前两者之差）。三者通过 SQL 计算，用于明确整单移除并非只移除金额偏差。

## 折扣驱动 analyze_discount_drivers

REST POST `/api/v1/tools/analyze_discount_drivers`，MCP `analyze_discount_drivers(request)`。MetricCompareRequest + SUM利润、完整 mapping（含 order），dimensions 最多4个额外维度（商品视图总是包含）。`exclude_amount_mismatches=true` 默认按金额/利润账式差额（amount_tolerance 默认0.01）选全量订单并整单排除；可设 false，或用 exclude_order_ids（最多100个）追加明确订单。两期必须都有保留记录，剩余利润账式仍需成立。不得把排除后的订单自动称为正常。

返回 original_comparison、保留范围 comparison、selection、excluded_order_ids（最多500并标记截断）、profit_bridge、views、focus、evidence v2。每个维度的全量贡献独立对账到同一 profit_bridge.discount_effect，不可跨维度累加。top_k（默认10、最大100）控制每个维度成员展示，保留 omitted_contribution 和 reconciliation_error；按贡献绝对值排序。

### 数学口径

共享利润桥按商品 s 计算折扣项 `−K_s × (d_s1−d_s0)`，其中 `K_s=平均总销量×平均商品销量份额×平均商品标价`；商品折扣 d 按标价销售额 q×p 加权。对每个额外维度，在商品内令成员份额 w 为该成员标价销售额/该商品标价销售额，成员折扣 r 为按 q×p 加权的减免比例。二因素对称中点恒等式：

- rate_effect = `−K_s × 平均(w) × Δr`（同成员同商品折扣率变化）；
- structure_effect = `−K_s × 平均(r) × Δw`（同商品内转向不同折扣成员）；
- 跨商品求和得到成员贡献，再跨成员求和得到该视图的完整折扣贡献。

商品视图本身不再拆商品间结构；商品间结构在 profit_bridge.mix_effect 已独立计算。成员整体折扣率可能受商品组合变化影响，不能直接替代同商品比较。新增/消失成员沿用另一期间已观测折扣率，仅为交互项分摊约定；实际缺失率保留 null。商品缺失一整期时沿用对侧价格/折扣和成员分布以保持共享利润桥口径；有销量但标价销售额为零时折扣按0分摊。零价/新旧成员场景有回归测试。这是账式分摊，不是识别因果干预效应。

### 保留比较基准的下钻

`focus_dimension` 与 `focus_member` 成对传入，且维度必须属于商品或本次请求维度。focus只筛明细，绝不改变参考集、排除集合或系数。返回逐商品实际折扣率、同商品内份额、系数、两类贡献、缺失率分摊标记，并给出对应订单×商品的销售/利润及加权折扣。商品和订单明细各最多100项，分别返回截断标记。`views[].rows[].drilldown` 是可直接调用的请求；null成员不提供该字符串入口，但保留全量贡献。核查应查合同、促销、客户等级与审批，不把贡献解释为已证实违规。

每个视图 totals 额外返回 product_member_cells、comparable_rate_cells、missing_rate_cells，披露商品×成员的两期实际折扣率覆盖。高比例缺失时，结构项受沿用率约定影响，应优先核查数据覆盖和成员更替，不能把它直接当作已识别的客户结构因果效应。

## 折扣订单专项 audit_discount_orders

REST POST `/api/v1/tools/audit_discount_orders`；MCP `audit_discount_orders(request)`。共享 MetricCompareRequest、SUM利润和完整 mapping；另需 customer_column、channel_column。filters 用于区域等固定范围；product_ids 可选择目标商品（最多100，空为全部）。默认自动整单排除金额/利润账式异常，也可通过 exclude_order_ids 增补（最多100）或关闭 exclude_amount_mismatches。无当期保留目标行时拒绝；没有足够基期参考不编造基准。

基期参考按标价销售额加权，依次选择同商品×客户×渠道、同商品×渠道、同商品。每层至少 min_reference_orders 个不同订单（默认3，不以行数代替订单数），分母非零才可用。回退后的数值是同群基准，不证明同客户实际加深。reference_coverage 返回层级、行数与覆盖金额；订单及明细返回参考层级、基期订单数、无参考行数。

`discount_burden=当期数量×标价×(实际减免比例−参考比例)`，正值表示固定当期价格/数量/成本下毛利被压低。它不是同比变化贡献、因果效果或可追回金额。deeper_discount_amount 仅累加正偏差，discount_burden 保留正负抵消。基期折扣情景毛利=gross×(1−参考率)−成本；不亏损折扣上限=1−成本/gross，零gross时未定义，上限为负表示原价也不能覆盖成本。未包含期间费用，不叫净利润。

目标商品毛利与当前filters/窗口内整单全部商品毛利分别计算；整单不保证包括范围外的明细。P0_ACCOUNTING 优先复核目标或整单其他商品的金额账式；P1_LOSS 表示范围整单亏损且未折扣公式毛利非负，即使无基期参考也优先核查，但不得声称已经证明折扣加深。P2_SELECTED_LOSS 是目标商品亏损且有超基准折扣，整单未必亏损；P2_MATERIAL 是正向超基准折扣额达到 materiality（默认500源单位）。参考不足归P3_REFERENCE，其余P3_ROUTINE。规则和原因随结果返回，不构成违规结论。

输出 audit_summary（全量当期订单、目标毛利、基准金额、范围整单亏损数/亏损毛利、优先级数）、orders、sku/customer/channel breakdown、reference_coverage、priority_rules、focus及 evidence v2。top_k 默认20、最大100，按优先级和正向超基准金额排序；统计不受截断影响，各维度不可叠加。focus_order_id只筛明细，保留参考与优先级；返回目标商品与当前范围整单全部商品明细，各最多100行并标记截断。orders[].drilldown 可直接再次调用。NULL参考不按零填充，汇总基准金额只覆盖可评分行。

客户/渠道 breakdown 成员也返回 drilldown，可用 focus_customer、focus_channel 展开相关订单；这些参数仅筛证据，不重算基期参考。多项focus条件按AND组合。整单证据返回目标集合涉及的订单全部范围内明细并含 oid。selected_loss_orders 单独记录目标商品毛利为负的订单数。排序使用显式 priority_rank：账式问题→整单亏损→目标商品亏损→金额门槛→参考不足→常规，避免字符串排序把金额较大订单放在目标商品亏损之前。


### 折扣保本与情景压力工具 `simulate_discount_scenarios`
REST `POST /api/v1/tools/simulate_discount_scenarios` 与同名 MCP 共用 DiscountScenarioRequest、SQL 计算和 v2 evidence；只读，无 Agent 循环。继承 audit_discount_orders 的指标、时间、映射、过滤、排除与三级基期参考。`order_ids` 仅筛明细，不改变总体情景；focus 字段不参与情景计算。

输入 `discount_caps` 减免比例列表（默认 .1/.2/.3/.35），`volume_reductions` 假设销量下降列表（默认 0/.05/.1/.2，始终含零），`variable_cost_share` 成本可变比例（默认 1，业务需确认），均为有限 0–1 值；每列表最多12项。负数量不适用，账式不兼容需修复或排除。

对每行 G=数量×标价，d=实际减免，c=上限，v=降量，C=映射成本，a=可变成本比例：新减免=min(d,c)，情景毛利=G×(1−min(d,c))×(1−v)−C×(1−a×v)。其余商品不变。uplift 相比原公式毛利 G×(1−d)−C；versus_actual 相比实际毛利，另含账式舍入差。保持原公式毛利的容忍降量=固定销量改善/Σ[G×(1−min(d,c))−aC]，分母非正返回 null，超过100%保持原值解释，不能当作需求预测。

订单目标商品统一折扣保本线=1−ΣC/ΣG；范围整单线=1−(ΣC−其他商品实际毛利)/ΣG。零标价分母返回 null，负阈值表示零折扣也亏损。实际执行应向下取整。恢复基期按每行三级参考率执行，参考缺失则整单 restore_uplift/restored_whole_profit 为 null；不是保证收益。成本未含未映射税费/期间费用。

输出 scenario_selection（排除、覆盖、账式差），全量 scenarios、product_scenarios，scenario_orders（保本、恢复、audit 下钻），scenario_lines（参考层级、订单数、原始字段），next_checks；图表区分固定销量与销量压力。商品明细最多2500项、订单/行最多100项，truncation 明示，不影响总体聚合。销量压力是假设而非弹性估计；核查合同、折扣授权、可比基期、成本可变比例与客户流失风险后再评估实施。


#### 多成本销量风险边界（simulate_discount_scenarios 扩展）
REST 路径及 MCP 工具名不变，保留 variable_cost_share 单情景字段兼容旧调用。新增 cost_share_cases（默认 [0,.5,1]，1–5项有限0–1比例）和 robustness_volume_drop（默认 .2）。全量 SQL 按组合及每个商品计算，order_ids 仍只筛订单证据。返回 risk_frontiers、robustness、成本案例及压力参数；图表将维持原毛利与保本明确分开。

令新收入 R=ΣG(1−min(d,cap))，成本 C=Σ成本，原公式毛利 B，成本可变比例 a；降量v下 P(v)=R−C−v(R−aC)。零降量毛利 P0=R−C，斜率 L=R−aC。
- 维持原毛利代数根 (P0−B)/L（L>0）；可行最大降量限制在[0,1]，L<=0时因收紧折扣不降低初始毛利，全区间可保持。
- 零毛利代数根 P0/L（L不为0），原值保留，不将域外根伪装为可实现临界点。
- nonloss_max_drop 仅在P0>=0时定义：L>0为min(1,P0/L)，否则为1。P0<0返回null和initial_loss，不能当作可容忍降量；亏损业务可能在100%停销量后归零，但这不是从盈利转亏的边界。L=0且P0=0为全区间零毛利，代数根null。
- robustness 根据配置压力v，检查全部成本案例以及每个商品。passes_all_cases 要求毛利和较B改善均非负（浮点容差1e-8）；total_only 表示仅组合通过；profit_erodes 表示组合仍盈利但改善被吃掉；loss_risk表示组合有亏损案例。商品×成本退化/亏损计数不可当作不同商品数。

边界是目标商品映射成本口径，非企业净利润。短期固定成本、最低采购承诺、库存与运费应由业务核查。不同上限会有不同需求反应，工具不估计弹性；相同降量压力下数学更优不等于最严格上限应实施。总量稳健性全量计算，风险明细最多2500项且truncation标记。报告使用金色维持毛利线/绿色保本带、统一0–100%横轴和逐商品展开对照。
