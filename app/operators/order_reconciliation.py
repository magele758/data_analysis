"""Evidence-based order amount hypotheses and exact exclusion profit bridges."""
from types import SimpleNamespace
from app.operators.analytical_tools import Context
from app.operators.business_report import quote, literal
from app.operators.profit_decomposition import profit_bridge
from app.schemas.requests import OrderReconciliationRequest


def reconcile_order_amounts(req: OrderReconciliationRequest):
    m=req.mapping
    ctx=Context(req,[req.line_id,*req.adjustments,*[v for k,v in m.model_dump().items() if k!='discount_scale' and v]])
    comparison=ctx.compare()
    n=lambda key:f'TRY_CAST({quote(getattr(m,key))} AS DOUBLE)'
    adj='+'.join(f'TRY_CAST({quote(c)} AS DOUBLE)' for c in req.adjustments) or 'NULL::DOUBLE'
    line_id=f'CAST({quote(req.line_id)} AS VARCHAR)' if req.line_id else 'NULL::VARCHAR'
    cte=ctx.cte+f""", forensic_lines AS (SELECT __da_id,__da_date,__da_period,
      CAST({quote(m.order)} AS VARCHAR) AS oid,CAST({quote(m.product)} AS VARCHAR) AS product,{line_id} AS line_id,
      {n('quantity')} AS q,{n('price')} AS price,{n('discount')}/{m.discount_scale} AS discount,
      {n('sales')} AS sales,{n('cost')} AS cost,TRY_CAST({quote(req.metric.column)} AS DOUBLE) AS profit,
      {adj} AS adjustments FROM data),
      amounts AS (SELECT *,q*price*(1-discount) AS expected_sales,sales-expected_sales AS amount_gap,
        profit-(sales-cost) AS ledger_gap FROM forensic_lines),
      duplicate_checks AS (SELECT *,COUNT(*) OVER(PARTITION BY oid,__da_date,product,q,price,discount,sales,cost,profit) AS same_business_values,
        CASE WHEN line_id IS NOT NULL THEN COUNT(*) OVER(PARTITION BY oid,line_id) END AS same_line_id FROM amounts),
      targets AS (SELECT DISTINCT oid FROM amounts WHERE {('oid IN ('+','.join(literal(x) for x in req.order_ids)+')') if req.order_ids else f'ABS(amount_gap)>{req.amount_tolerance} OR ABS(ledger_gap)>{req.amount_tolerance}'})"""
    invalid=ctx.query(cte+''' SELECT COUNT(*) AS n FROM forensic_lines WHERE oid IS NULL OR product IS NULL OR NOT COALESCE(
      ISFINITE(q) AND q>0 AND ISFINITE(price) AND price>=0 AND ISFINITE(discount) AND discount BETWEEN 0 AND 1
      AND ISFINITE(sales) AND ISFINITE(cost) AND cost>=0,FALSE)''')[0]['n']
    if invalid:raise ValueError(f'{invalid} invalid mapping rows; fix mappings/returns before reconciliation')
    ratios=' UNION ALL '.join(f'SELECT {v}::DOUBLE AS multiplier' for v in req.multipliers) or 'SELECT NULL::DOUBLE AS multiplier WHERE FALSE'
    scope=cte+f''', factors AS ({ratios}), diagnosed AS (SELECT *,sales/NULLIF(expected_sales,0) AS observed_multiplier,
      sales-(q*price) AS undiscounted_gap,sales-(q*price*discount) AS retained_discount_gap,
      CASE WHEN ISFINITE(adjustments) THEN amount_gap-adjustments END AS unexplained_after_adjustments,
      (SELECT LIST(multiplier ORDER BY multiplier) FROM factors WHERE ABS(expected_sales)> {req.amount_tolerance}
       AND ABS(sales-expected_sales*multiplier)<={req.amount_tolerance}) AS matching_multipliers
      FROM duplicate_checks WHERE oid IN (SELECT oid FROM targets))'''
    orders=ctx.query(scope+''' SELECT oid,MIN(__da_date) AS first_date,COUNT(*) AS lines,SUM(profit) AS profit,
      SUM(amount_gap) AS amount_gap,SUM(ABS(amount_gap)) AS absolute_amount_gap,
      SUM(ABS(ledger_gap)) AS absolute_ledger_gap,
      COUNT(*) FILTER(WHERE same_business_values>1) AS repeated_business_rows,
      COUNT(*) FILTER(WHERE same_line_id>1) AS repeated_line_id_rows,
      COUNT(*) OVER() AS matched_orders FROM diagnosed GROUP BY oid ORDER BY ABS(SUM(amount_gap)) DESC,oid''',req.limit)
    rows=ctx.query(scope+f''' SELECT *,COUNT(*) OVER() AS matched_lines FROM diagnosed
      ORDER BY ABS(amount_gap) DESC,oid,__da_id LIMIT {req.limit}''',req.limit)
    counts=ctx.query(scope+''' SELECT COUNT(*) AS selected_lines,COUNT(DISTINCT oid) AS selected_orders,
      COUNT(*) FILTER(WHERE ISFINITE(adjustments)) AS adjustment_covered_lines,
      COUNT(*) FILTER(WHERE __da_period='base') AS removed_base_rows,
      COUNT(*) FILTER(WHERE __da_period='current') AS removed_current_rows FROM diagnosed''')[0]
    bridges=[];checks=[]
    proxy=SimpleNamespace(mapping=m,time_column=req.time.column,metric=req.metric.column)
    t=req.time;b=f"__date>=DATE '{t.base_start}' AND __date<DATE '{t.base_end}'";c=f"__date>=DATE '{t.current_start}' AND __date<DATE '{t.current_end}'"
    for scenario,condition in [('original','TRUE'),('excluding_selected',f'CAST({quote(m.order)} AS VARCHAR) NOT IN (SELECT oid FROM targets)')]:
        table=f'({cte} SELECT * REPLACE(__da_date AS {quote(t.column)}) FROM data WHERE {condition})'
        result,_,messages=profit_bridge(proxy,table,'',b,c,lambda key,sql,limit=2500:ctx.query(sql,limit))
        if result:
            row=next(x for x in result if x['scenario']=='reported')
            if not row['comparable']:
                # Empty period is not zero business; bridge cannot be interpreted.
                for key in list(row):
                    if key.endswith('_effect') or key in ('delta','change_pct','reconciliation_error'):row[key]=None
            bridges.append({**row,'scenario':scenario})
        else:checks.extend(f'{scenario}: {x}' for x in messages)
    effect_changes=[]
    if len(bridges)==2 and all(x['comparable'] for x in bridges):
        for k in ['volume_effect','mix_effect','price_effect','discount_effect','cost_effect','residual_effect','ledger_effect','delta']:
            # Difference is computed by SQL, as are all evidence amounts.
            difference=ctx.query(f"SELECT CAST({bridges[1][k]}-({bridges[0][k]}) AS DOUBLE) AS difference")[0]['difference']
            effect_changes.append({'factor':k,'original':bridges[0][k],'excluding_selected':bridges[1][k],'difference':difference})
    exclusion_summary=None
    if effect_changes:
        changes={x['factor']:x['difference'] for x in effect_changes}
        exclusion_summary=ctx.query(f"SELECT {changes['delta']}::DOUBLE AS delta_difference,{changes['residual_effect']}::DOUBLE AS residual_difference,({changes['delta']}-({changes['residual_effect']}))::DOUBLE AS other_factor_difference")[0]
    ctx.warnings.extend(checks+[
      '重复检测覆盖当前窗口/筛选范围；同业务字段重复可能是合法拆行，重复行号也需核查主键范围。没有重复特征不能排除上游重复导入。',
      '倍率仅匹配调用方候选及金额容差；观察倍率或匹配倍数不证明单位错误。未折扣/折扣含义反转均为待验证口径假设。',
      '税费/运费仅使用调用方映射的逐行有符号附加金额。无字段或缺失值则未知，不猜税率；订单总税费不可重复填在每一行。',
      '排除比较删除所选订单在当前范围内的全部行，既移除异常金额也移除其正常业务。结果是敏感性，不是纠错后的真实利润；剩余业务也不自动等于正常业务。'])
    return ctx.envelope('reconcile_order_amounts','duplicate_multiplier_adjustment_and_exclusion_bridge',{
      'comparison':comparison,'selection':counts,'orders':orders,'line_evidence':rows,
      'tax_fee_status':'mapped_line_adjustments' if req.adjustments else 'unknown_missing_fields',
      'duplicate_id_status':'mapped' if req.line_id else 'unknown_missing_line_id',
      'profit_bridges':bridges,'effect_changes':effect_changes,'exclusion_summary':exclusion_summary,'skipped':checks},
      {'truncated':counts['selected_lines']>len(rows) or counts['selected_orders']>len(orders),'returned_lines':len(rows),'total_lines':counts['selected_lines'],'returned_orders':len(orders),'total_orders':counts['selected_orders']})
