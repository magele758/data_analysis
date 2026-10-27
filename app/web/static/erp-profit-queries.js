/* Read-only analytical queries executed by the existing session SQL operator. */
(() => {
  'use strict';
  const scopes = {all:'TRUE',south:"region = 'South'",westTech:"region = 'West' AND category = 'Technology'"};
  function source(scope='all') {
    if (!(scope in scopes)) throw new Error('未知分析范围');
    return `WITH source AS (SELECT *, sales-quantity*unit_price*(1-discount) AS residual FROM erp_sales
      WHERE CAST(order_date AS DATE) >= DATE '2024-01-01' AND CAST(order_date AS DATE) < DATE '2026-01-01'),
      flagged AS (SELECT DISTINCT order_id FROM source WHERE ABS(residual)>0.01),
      scoped AS (SELECT * FROM source WHERE ${scopes[scope]})`;
  }
  function bridge(scope='all') {
    return `${source(scope)},
      samples AS (SELECT 'reported' AS scenario,* FROM scoped UNION ALL SELECT 'review' AS scenario,* FROM scoped WHERE order_id NOT IN (SELECT order_id FROM flagged)),
      g AS (SELECT scenario,product_id,EXTRACT(YEAR FROM CAST(order_date AS DATE)) AS yr,
        SUM(quantity)::DOUBLE AS q,SUM(quantity*unit_price)/NULLIF(SUM(quantity),0) AS p,
        SUM(quantity*unit_price*discount)/NULLIF(SUM(quantity*unit_price),0) AS d,
        SUM(cogs)/NULLIF(SUM(quantity),0) AS c,SUM(residual) AS r,SUM(profit) AS profit,
        SUM(profit-(sales-cogs)) AS ledger_gap
        FROM samples GROUP BY ALL),
      pairs AS (SELECT scenario,product_id,
        COALESCE(MAX(q) FILTER(WHERE yr=2024),0) AS q0,COALESCE(MAX(q) FILTER(WHERE yr=2025),0) AS q1,
        COALESCE(MAX(p) FILTER(WHERE yr=2024),MAX(p) FILTER(WHERE yr=2025)) AS p0,
        COALESCE(MAX(p) FILTER(WHERE yr=2025),MAX(p) FILTER(WHERE yr=2024)) AS p1,
        COALESCE(MAX(d) FILTER(WHERE yr=2024),MAX(d) FILTER(WHERE yr=2025)) AS d0,
        COALESCE(MAX(d) FILTER(WHERE yr=2025),MAX(d) FILTER(WHERE yr=2024)) AS d1,
        COALESCE(MAX(c) FILTER(WHERE yr=2024),MAX(c) FILTER(WHERE yr=2025)) AS c0,
        COALESCE(MAX(c) FILTER(WHERE yr=2025),MAX(c) FILTER(WHERE yr=2024)) AS c1,
        COALESCE(SUM(r) FILTER(WHERE yr=2025),0)-COALESCE(SUM(r) FILTER(WHERE yr=2024),0) AS residual_effect,
        COALESCE(SUM(ledger_gap) FILTER(WHERE yr=2025),0)-COALESCE(SUM(ledger_gap) FILTER(WHERE yr=2024),0) AS ledger_effect,
        COALESCE(SUM(profit) FILTER(WHERE yr=2024),0) AS base_profit,
        COALESCE(SUM(profit) FILTER(WHERE yr=2025),0) AS current_profit
        FROM g GROUP BY scenario,product_id),
      totals AS (SELECT *,SUM(q0) OVER(PARTITION BY scenario) AS Q_base,SUM(q1) OVER(PARTITION BY scenario) AS Q_current,
        p0*(1-d0)-c0 AS m0,p1*(1-d1)-c1 AS m1 FROM pairs),
      effects AS (SELECT *,q0/NULLIF(Q_base,0) AS s0,q1/NULLIF(Q_current,0) AS s1 FROM totals),
      result AS (SELECT scenario,MAX(Q_base) AS base_quantity,MAX(Q_current) AS current_quantity,
        SUM(base_profit) AS base_profit,SUM(current_profit) AS current_profit,
        SUM((Q_current-Q_base)*(s0*m0+s1*m1)/2) AS volume_effect,
        SUM((Q_base+Q_current)/2*(s1-s0)*(m0+m1)/2) AS mix_effect,
        SUM((Q_base+Q_current)/2*(s0+s1)/2*(p1-p0)*(1-(d0+d1)/2)) AS price_effect,
        SUM(-(Q_base+Q_current)/2*(s0+s1)/2*(p0+p1)/2*(d1-d0)) AS discount_effect,
        SUM(-(Q_base+Q_current)/2*(s0+s1)/2*(c1-c0)) AS cost_effect,
        SUM(residual_effect) AS residual_effect,SUM(ledger_effect) AS ledger_effect
        FROM effects GROUP BY scenario)
      SELECT *,current_profit-base_profit AS delta,
        (current_profit-base_profit)/NULLIF(ABS(base_profit),0)*100 AS change_pct,
        current_profit-base_profit-volume_effect-mix_effect-price_effect-discount_effect-cost_effect-residual_effect-ledger_effect AS reconciliation_error,
        base_quantity>0 AND current_quantity>0 AS comparable FROM result ORDER BY scenario`;
  }
  function orders(scope='all') {
    return `${source(scope)}, grouped AS (
      SELECT order_id,MIN(order_date) AS order_date,MIN(region) AS region,COUNT(*) AS lines,
        SUM(CASE WHEN ABS(residual)>0.01 THEN 1 ELSE 0 END) AS flagged_lines,
        SUM(sales) AS sales,SUM(profit) AS profit,SUM(residual) AS amount_gap
      FROM source WHERE order_id IN (SELECT order_id FROM flagged) AND order_id IN (SELECT order_id FROM scoped) GROUP BY order_id)
      SELECT *,COUNT(*) OVER() AS total_flagged_orders FROM grouped ORDER BY ABS(amount_gap) DESC LIMIT 20`;
  }
  function time(grain='month',scope='all') {
    if (!['day','week','month','quarter','year'].includes(grain)) throw new Error('未知时间粒度');
    return `${source(scope)},calendar AS (
      SELECT DISTINCT DATE_TRUNC('${grain}',day)::DATE AS period FROM generate_series(DATE '2024-01-01',DATE '2025-12-31',INTERVAL '1 day') AS t(day)),
      g AS (SELECT DATE_TRUNC('${grain}',CAST(order_date AS DATE))::DATE AS period,
        SUM(profit) AS profit,SUM(sales) AS sales,SUM(quantity) AS quantity,SUM(cogs) AS cogs,
        SUM(quantity*unit_price*discount) AS discounts,SUM(quantity*unit_price) AS list_sales,
        SUM(residual) AS amount_gap,COUNT(DISTINCT order_id) AS orders,
        SUM(profit) FILTER(WHERE order_id NOT IN (SELECT order_id FROM flagged)) AS reviewed_profit
        FROM scoped GROUP BY 1),series AS (
      SELECT c.period,COALESCE(g.profit,0) AS profit,COALESCE(g.sales,0) AS sales,COALESCE(g.quantity,0) AS quantity,
        g.profit/NULLIF(g.sales,0)*100 AS margin,g.sales/NULLIF(g.quantity,0) AS net_unit_price,
        g.cogs/NULLIF(g.quantity,0) AS unit_cost,g.discounts/NULLIF(g.list_sales,0)*100 AS discount_pct,
        COALESCE(g.orders,0) AS orders,COALESCE(g.reviewed_profit,0) AS reviewed_profit,
        COALESCE(g.amount_gap,0) AS amount_gap,g.period IS NOT NULL AS has_records
      FROM calendar c LEFT JOIN g USING(period))
      SELECT a.*,a.profit-LAG(a.profit) OVER(ORDER BY a.period) AS previous_delta,
        (a.profit-LAG(a.profit) OVER(ORDER BY a.period))/NULLIF(ABS(LAG(a.profit) OVER(ORDER BY a.period)),0)*100 AS previous_pct,
        ${grain==='week'?'NULL':'a.profit-b.profit'} AS yoy_delta,
        ${grain==='week'?'NULL':'(a.profit-b.profit)/NULLIF(ABS(b.profit),0)*100'} AS yoy_pct
      FROM series a LEFT JOIN series b ON b.period=(a.period-INTERVAL '1 year')::DATE ORDER BY a.period`;
  }
  window.ERPProfitQueries={bridge,orders,time};
})();
