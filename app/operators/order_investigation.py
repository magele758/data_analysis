"""Read-only order reconciliation and cohort checks; classification is not fraud proof."""
from app.operators.analytical_tools import Context
from app.operators.business_report import quote, literal
from app.schemas.requests import OrderInvestigationRequest


def investigate_orders(req: OrderInvestigationRequest):
    m=req.mapping
    ctx=Context(req,[req.anomaly_column,req.group_by,*[v for k,v in m.model_dump().items() if k!='discount_scale' and v]])
    comparison=ctx.compare()
    n=lambda k:f'TRY_CAST({quote(getattr(m,k))} AS DOUBLE)'
    threshold=req.threshold if req.threshold is not None else {'mad':3.5,'iqr':1.5,'zscore':3}[req.method]
    group=f'CAST({quote(req.group_by)} AS VARCHAR)' if req.group_by else "'all'"
    ref="WHERE __da_period='base'" if req.reference=='base' else ''
    cte=ctx.cte+f""", lines AS (SELECT __da_period,__da_date,__da_id,CAST({quote(m.order)} AS VARCHAR) AS oid,
      CAST({quote(m.product)} AS VARCHAR) AS product,{group} AS cohort,
      {n('quantity')} AS q,{n('price')} AS price,{n('discount')}/{m.discount_scale} AS discount,
      {n('sales')} AS sales,{n('cost')} AS cost,TRY_CAST({quote(req.metric.column)} AS DOUBLE) AS profit,
      TRY_CAST({quote(req.anomaly_column)} AS DOUBLE) AS x FROM data),
      stats AS (SELECT cohort,COUNT(x) FILTER(WHERE ISFINITE(x)) AS nr,MEDIAN(x) FILTER(WHERE ISFINITE(x)) AS med,
        STDDEV_POP(x) FILTER(WHERE ISFINITE(x)) AS sd,AVG(x) FILTER(WHERE ISFINITE(x)) AS avg,
        QUANTILE_CONT(x,0.25) FILTER(WHERE ISFINITE(x)) AS q1,QUANTILE_CONT(x,0.75) FILTER(WHERE ISFINITE(x)) AS q3 FROM lines {ref} GROUP BY cohort),
      mads AS (SELECT l.cohort,MEDIAN(ABS(x-med)) FILTER(WHERE ISFINITE(x)) AS mad FROM lines l JOIN stats s ON l.cohort IS NOT DISTINCT FROM s.cohort {ref} GROUP BY l.cohort),
      discount_ref AS (SELECT product,COUNT(*) AS dn,MEDIAN(discount) AS baseline_discount,QUANTILE_CONT(discount,0.25) AS d1,QUANTILE_CONT(discount,0.75) AS d3
        FROM lines WHERE __da_period='base' GROUP BY product),
      order_checked AS (SELECT l.*,s.nr,s.med,s.sd,s.avg,s.q1,s.q3,md.mad,dr.dn,dr.baseline_discount,
        {'CAST('+str(req.discount_threshold)+' AS DOUBLE)' if req.discount_threshold is not None else 'dr.d3+1.5*(dr.d3-dr.d1)'} AS discount_limit,
        sales-q*price*(1-discount) AS amount_gap,profit-(sales-cost) AS ledger_gap
        FROM lines l LEFT JOIN stats s ON l.cohort IS NOT DISTINCT FROM s.cohort
        LEFT JOIN mads md ON l.cohort IS NOT DISTINCT FROM md.cohort LEFT JOIN discount_ref dr USING(product)),
      flags AS (SELECT *,COALESCE(nr>=2 AND ISFINITE(x) AND {('mad>0 AND 0.6744897501960817*ABS(x-med)/mad>='+str(threshold)) if req.method=='mad' else ('sd>0 AND ABS(x-avg)/sd>='+str(threshold)) if req.method=='zscore' else ('(x<q1-'+str(threshold)+'*(q3-q1) OR x>q3+'+str(threshold)+'*(q3-q1))')},FALSE) AS candidate,
        ABS(amount_gap)>{req.amount_tolerance} OR ABS(ledger_gap)>{req.amount_tolerance} AS amount_issue,
        {'TRUE' if req.discount_threshold is not None else 'COALESCE(dn>='+str(req.min_reference_rows)+',FALSE)'} AS discount_scored FROM order_checked),
      orders AS (SELECT oid,__da_period AS period,MIN(__da_date) AS date,COUNT(*) AS lines,
        SUM(sales) AS sales,SUM(profit) AS profit,SUM(amount_gap) AS amount_gap,SUM(ABS(amount_gap)) AS absolute_amount_gap,
        SUM(ledger_gap) AS ledger_gap,SUM(ABS(ledger_gap)) AS absolute_ledger_gap,
        SUM(CASE WHEN discount_scored THEN q*price*GREATEST(discount-baseline_discount,0) END) AS excess_discount_amount,
        MAX(discount) AS max_discount,MIN(discount_limit) AS min_discount_limit,
        BOOL_OR(candidate) AS candidate,BOOL_OR(amount_issue) AS amount_issue,
        BOOL_OR(discount_scored AND discount>discount_limit) AS discount_issue,
        BOOL_AND(discount_scored) AS discount_scored FROM flags GROUP BY oid,__da_period),
      size_ref AS (SELECT COUNT(*) AS size_n,QUANTILE_CONT(sales,0.75)+1.5*(QUANTILE_CONT(sales,0.75)-QUANTILE_CONT(sales,0.25)) AS large_limit FROM orders WHERE period='base'),
      classified AS (SELECT *,CASE WHEN amount_issue THEN 'amount_mismatch' WHEN discount_issue THEN 'discount_outlier'
        WHEN NOT discount_scored OR size_n<{req.min_reference_rows} THEN 'insufficient_evidence'
        WHEN sales>large_limit THEN 'large_order_checks_passed' ELSE 'other_checks_passed' END AS category
        FROM orders CROSS JOIN size_ref)"""
    invalid=ctx.query(cte+''' SELECT COUNT(*) AS n FROM lines WHERE oid IS NULL OR product IS NULL OR NOT COALESCE(
      ISFINITE(q) AND q>0 AND ISFINITE(price) AND price>=0 AND ISFINITE(discount) AND discount BETWEEN 0 AND 1
      AND ISFINITE(sales) AND ISFINITE(cost) AND cost>=0,FALSE)''')[0]['n']
    if invalid:raise ValueError(f'{invalid} invalid order mapping rows; fix missing IDs, return quantities, amounts or discount scale before investigation')
    categories=ctx.query(cte+''' SELECT category,COUNT(*) AS order_periods,COUNT(*) FILTER(WHERE candidate) AS candidate_order_periods,
      COALESCE(SUM(profit) FILTER(WHERE period='base'),0) AS base_profit,
      COALESCE(SUM(profit) FILTER(WHERE period='current'),0) AS current_profit,
      current_profit-base_profit AS contribution,
      COALESCE(SUM(amount_gap) FILTER(WHERE period='current'),0)-COALESCE(SUM(amount_gap) FILTER(WHERE period='base'),0) AS amount_gap_change,
      SUM(absolute_amount_gap) AS absolute_amount_gap,
      SUM(excess_discount_amount) FILTER(WHERE period='base') AS base_excess_discount_amount,
      SUM(excess_discount_amount) FILTER(WHERE period='current') AS current_excess_discount_amount FROM classified GROUP BY category ORDER BY contribution''')
    reconciliation=ctx.query(cte+f''' SELECT SUM(CASE WHEN period='current' THEN profit ELSE -profit END)-({comparison['delta']}) AS error,
      COUNT(*) AS total_order_periods,COUNT(*) FILTER(WHERE candidate) AS candidate_order_periods,
      COUNT(*) FILTER(WHERE amount_issue AND discount_issue) AS overlapping_issues FROM classified''')[0]
    # Order IDs filter only the evidence page, never the reference or contributions.
    where='WHERE oid IN ('+','.join(literal(x) for x in req.order_ids)+')' if req.order_ids else ''
    orders=ctx.query(cte+f''' SELECT *,COUNT(*) OVER() AS matched_orders FROM classified {where}
      ORDER BY candidate DESC,ABS(profit) DESC,oid,period LIMIT {req.limit}''')
    evidence_lines=[]
    if req.order_ids:
        evidence_lines=ctx.query(cte+f''' SELECT oid,__da_period AS period,__da_date AS date,product,q,price,discount,baseline_discount,discount_limit,dn AS reference_rows,
          sales,cost,profit,amount_gap,ledger_gap,candidate,discount_scored FROM flags
          WHERE oid IN ({','.join(literal(x) for x in req.order_ids)}) ORDER BY oid,__da_date,__da_id LIMIT 501''',501)
    for row in orders:
        row['drilldown']={'tool':'investigate_orders','request':{**req.model_dump(mode='json'),'order_ids':[row['oid']]}}
    ctx.warnings.extend([
      '分类按订单×期间互斥：金额不一致优先，其次折扣异常、证据不足、大单检查通过、其他检查通过；重叠标记仍保留，不能把多项标记重复相加。',
      '折扣参考同商品基期四分位围栏（或调用方固定阈值）；大单参考基期订单销售额围栏。检查通过不代表合同、审批、履约已验证，不得直接称为正常订单。',
      '候选复现所选异常检测规则并扩展至订单；类别贡献覆盖全部订单，避免只看异常候选。贡献=当期利润−基期利润，不是因果效应。',
      '折扣超基准金额=数量×标价×max(折扣−同商品基期折扣中位数,0)，仅作固定数量价格的诊断基准，不是可追回损失；不可与利润贡献相加。分类构成变化也会影响类别贡献，折扣异常类贡献为正不表示折扣改善利润。',
      '订单核查仅包含当前窗口和过滤范围；order_ids仅筛明细，不改变参考集。金额差额是账式残差，不自动等于可追回损失。'])
    return ctx.envelope('investigate_orders','order_accounting_and_baseline_checks',{
      'comparison':comparison,'categories':categories,'reconciliation':reconciliation,'orders':orders,
      'line_evidence':evidence_lines[:500],'line_evidence_truncated':len(evidence_lines)>500,
      'next_checks':['金额不一致：核对原始发票、税费、运费、币种和销售金额公式。','折扣异常：核对同商品合同价、促销及折扣审批，不能以偏离阈值判违规。','大单检查通过：核对交付、回款和是否一次性订单；基期大单不再出现也会拉低同比。']},
      {'truncated':bool(orders and orders[0]['matched_orders']>len(orders)),'returned':len(orders),'total':orders[0]['matched_orders'] if orders else 0,'line_evidence_truncated':len(evidence_lines)>500})
