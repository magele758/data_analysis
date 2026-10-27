/* ERP report presentation. All aggregates, tests and contributions come from service operators. */
(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = x => typeof x==='number'&&Number.isFinite(x)?x.toLocaleString('zh-CN',{maximumFractionDigits:2}):'—';
  const signed = x => (x>0?'+':'')+number(x);
  function bars(rows){
    const scale=Math.max(1,...rows.map(r=>Math.abs(r.diff_value)));
    return '<div class="erp-bars" role="list">'+rows.map((r,i)=>'<button type="button" role="listitem" class="erp-bar-row" data-contribution="'+i+'" aria-label="'+esc(r.dimension_value+'，贡献 '+signed(r.diff_value))+'"><span>'+esc(r.dimension_value)+'</span><span class="erp-bar-track"><i class="'+(r.diff_value>0?'positive':'negative')+'" style="width:'+Math.abs(r.diff_value)/scale*48+'%"></i></span><b>'+signed(r.diff_value)+'</b></button>').join('')+'</div><div class="erp-bar-legend">旧金：利润减少 ← 零基线 → 青灰：利润增加</div>';
  }
  function heatmap(rows){
    const regions=[...new Set(rows.map(r=>r.dimension_path?.region))].filter(Boolean),categories=[...new Set(rows.map(r=>r.dimension_path?.category))].filter(Boolean);
    const scale=Math.max(1,...rows.map(r=>Math.abs(r.diff_value)));
    return '<div class="erp-heat-scroll"><table class="erp-heat"><caption>区域 × 品类的利润变化金额 · 2025 相对 2024</caption><thead><tr><th>区域</th>'+categories.map(c=>'<th>'+esc(c)+'</th>').join('')+'</tr></thead><tbody>'+regions.map(region=>'<tr><th>'+esc(region)+'</th>'+categories.map(category=>{const r=rows.find(r=>r.dimension_path?.region===region&&r.dimension_path?.category===category);if(!r)return '<td>未返回</td>';return '<td style="background:rgba('+(r.diff_value>0?'99,145,125':'176,139,75')+','+(.12+Math.abs(r.diff_value)/scale*.52)+')">'+signed(r.diff_value)+'</td>'}).join('')+'</tr>').join('')+'</tbody></table></div><p class="erp-note">颜色越深，变化幅度越大；缺少的分组标记为未返回，不当作零。</p>';
  }
  function anomalies(insights){
    const rows=(insights.insights||[]).filter(i=>i.type==='anomaly');
    const max=Math.max(1,...rows.map(r=>r.evidence?.outlier_count||0));
    return rows.length?'<div class="erp-anomalies">'+rows.map(r=>'<div><span>'+esc((r.subject?.columns||[]).join('、')||r.title)+'</span><div><i style="width:'+((r.evidence?.outlier_count||0)/max*100)+'%"></i></div><b>'+number(r.evidence?.outlier_count)+' 个</b></div>').join('')+'</div><p class="erp-note">来自本次返回的洞察，可能已被 Top 8 排序截断。|Z-score| ≥ 3 筛查；离群不等于错误。</p>':'<p class="erp-note">本次返回的洞察中没有异常项，不等于已证明没有异常。</p>';
  }
  window.ERPReport = {async render(host,data,{api}){
    const panel=document.createElement('section');panel.className='erp-visual-report';panel.innerHTML='<p role="status">正在读取本次会话的贡献与检验证据…</p>';host.prepend(panel);
    const scope={session_id:data.session_id,dataset_name:data.dataset_name};
    try {
      // Same-session DuckDB connection: keep operator calls sequential.
      const response=await api('/tools/driver_analysis',{method:'POST',body:{...scope,target_metric:'profit',dimension_path:['region','category'],base_filter:"order_date < '2025-01-01'",current_filter:"order_date >= '2025-01-01'",agg_func:'SUM',top_k:50}});
      const d=response.statistics;
      let a=null,testError='';
      try {a=(await api('/tools/spss_test',{method:'POST',body:{...scope,test_type:'one_way_anova',dependent_var:'profit',group_var:'region',alpha:.05}})).statistics} catch(e){testError=e.message}
      if(!panel.isConnected)return;
      const regions=d.hierarchy?.[0]?.branches||[],cells=d.hierarchy?.[1]?.branches||[];
      const lead=d.hierarchy?.[0]?.[d.diff_total<0?'top_negative_drivers':'top_positive_drivers']?.[0];
      const detailed=d.hierarchy?.[1]?.[d.diff_total<0?'top_negative_drivers':'top_positive_drivers']?.[0];
      const insights=data.insights||{};
      panel.innerHTML='<header class="erp-report-head"><div><h2>先看问题，再看证据。</h2><p>'+number(data.rows)+' 条有效销售明细 · ERP 合成示例 · 2024 → 2025</p></div><span>本次会话计算</span></header><div class="erp-summary-band"><div><span>2024 利润</span><strong>'+number(d.base_total)+'</strong></div><div><span>2025 利润</span><strong>'+number(d.current_total)+'</strong></div><div><span>利润变化</span><strong>'+signed(d.diff_total)+'</strong></div><div><span>变化率</span><strong>'+signed(d.growth_rate_pct)+'%</strong></div></div><section class="erp-problem"><h3>'+esc(lead?lead.dimension_value+' 是主要'+(d.diff_total<0?'拖累':'拉动')+'项。':'查看利润变化的构成。')+'</h3><p>'+(lead?'贡献 '+signed(lead.diff_value)+'，占总变化 '+number(lead.contribution_percentage)+'%。':'')+(detailed?'进一步下钻到 '+esc(detailed.dimension_value)+'，贡献 '+signed(detailed.diff_value)+'。':'')+'</p><p class="erp-note">这是变化来源的定位，不是因果结论。下一步核对订单、折扣与成本，并检查极端订单是否放大波动。</p></section><div class="erp-chart-grid"><section class="erp-report-chart"><h3>哪个区域影响最大？</h3>'+bars(regions)+'<p class="erp-selection" role="status">点击贡献项，查看基期、当期与贡献依据。</p></section><section class="erp-report-chart"><h3>问题集中在哪类商品？</h3>'+heatmap(cells)+'</section></div><div class="erp-chart-grid"><section class="erp-report-chart"><h3>哪些指标需要核查？</h3>'+anomalies(insights)+'</section><section class="erp-report-chart erp-test"><h3>差异有多大，证据有多强？</h3>'+(a?'<div class="erp-test-values"><div><span>ANOVA p 值</span><strong>'+esc(a.p_value)+'</strong><small>统计阈值 0.05</small></div><div><span>效应量 η²</span><strong>'+esc(a.effect_size_eta_squared)+'</strong><small>产品门槛 0.01</small></div></div><p>'+(a.p_value<.05?(a.effect_size_eta_squared<.01?'p 值达到统计阈值，但区域效应较小，未达到产品的实际效应门槛。':'p 值与效应量都达到产品门槛。'):'未达到 p < 0.05 的统计阈值。')+'</p><p class="erp-note">检验比较各区域销售明细的平均利润；归因比较两个年份的利润总和，两者回答不同问题。常规 ANOVA 结论仍依赖独立性、方差等假设。</p>':'<p>检验暂未加载：'+esc(testError)+'</p>')+'</section></div><details class="erp-methods"><summary>本报告采用哪些方法？</summary><ol><li>四张 ERP 源表关联，过滤取消订单，构建销售明细事实表。</li><li>EDA 与四条质量断言检查规模、字段、缺失和指定规则。</li><li>区域 × 品类做 SUM 聚合；2024 / 2025 做加法贡献分解与层级下钻。</li><li>Pearson 相关与 BH 多重检验校正；单因素 ANOVA 同时展示 p 值和 η²。</li><li>RFM 以客户汇总最近购买、明细条数、消费额。现有分群规则允许重叠，不能画成占比饼图。</li><li>Copilot 筛查离群、相关、集中度与趋势，再按配置排序。洞察关系表示共享字段，不表示因果。</li></ol><p>排序方式：'+esc(insights.ranking_method||'未返回')+'。这份报告未自动执行根因实验、告警或外部写回。</p></details><details class="erp-methods"><summary>查看可视化的完整计算依据</summary><pre></pre></details>';
      panel.querySelector('pre').textContent=JSON.stringify({session_id:data.session_id,dataset_name:data.dataset_name,driver:response,anova:a,insight_caveats:insights.caveats},null,2);
      panel.querySelectorAll('[data-contribution]').forEach(button=>button.addEventListener('click',()=>{const r=regions[Number(button.dataset.contribution)];panel.querySelector('.erp-selection').textContent=r.dimension_value+'：基期 '+number(r.base_value)+' → 当期 '+number(r.current_value)+'；变化 '+signed(r.diff_value)+'；贡献率 '+number(r.contribution_percentage)+'%。';panel.querySelectorAll('[data-contribution]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)))}));
    } catch(e) {panel.innerHTML='<p role="alert">可视化暂未加载：'+esc(e.message)+'。下方完整报告仍可阅读。</p>';}
  }};
})();
