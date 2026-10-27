/* Presentation only. Business aggregates and decomposition are computed by the SQL service. */
(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const n = x => x===null||x===undefined||!Number.isFinite(Number(x))?'—':Number(x).toLocaleString('zh-CN',{maximumFractionDigits:2});
  const signed = x => x==null?'—':(Math.abs(Number(x))<.005?'0':(x>0?'+':'')+n(x));
  const factors=[['volume_effect','销售件数'],['mix_effect','商品组合'],['price_effect','同品标价'],['discount_effect','折扣'],['cost_effect','单位成本'],['residual_effect','金额不一致'],['ledger_effect','利润账差']];
  const why={volume_effect:'核对销量与订单数、每单件数；销售件数增加不等于高毛利商品卖得更多。',mix_effect:'核对商品销售占比是否向低单位毛利商品迁移。新进/退出商品按另一期间的单位经济性补齐，影响记入件数与组合。',price_effect:'核对同一商品的合同标价、调价日期和币种；此处已把商品组合与折扣单列。',discount_effect:'核对折扣审批、促销时间、客户与渠道；先看 West / Technology 是否存在集中加深折扣。',cost_effect:'核对每件销售成本、采购与出库计价；本示例只有销售成本，无法解释人工、物流、固定费用。',residual_effect:'逐单对照 sales 与 quantity × unit_price × (1−discount)。可能涉及录入、税费、返利或口径；不是自动判错。',ledger_effect:'核对 profit 是否等于 sales − cogs；账差应先对账，再做经营解释。'};
  function waterfall(r){
    if(!r?.comparable)return '<p>两个年份都需要有正销售件数，当前范围无法进行可比的因素分解。</p>';
    let cursor=r.base_profit;
    const points=[{label:'2024 利润',value:r.base_profit,start:0,end:r.base_profit,total:true},...factors.map(([key,label])=>{const p={label,value:r[key],start:cursor,end:cursor+Number(r[key]),key};cursor=p.end;return p;}),{label:'2025 利润',value:r.current_profit,start:0,end:r.current_profit,total:true}];
    const low=Math.min(0,...points.map(p=>Math.min(p.start,p.end))),high=Math.max(1,...points.map(p=>Math.max(p.start,p.end))),y=v=>235-(v-low)/(high-low)*195;
    return '<div class="erp-wide-chart"><svg viewBox="0 0 980 300" role="img" aria-label="利润变化瀑布图，完整数值见下方因素表"><line x1="20" x2="965" y1="'+y(0)+'" y2="'+y(0)+'" stroke="#697461"/>'+points.map((p,i)=>{const x=27+i*106,top=Math.min(y(p.start),y(p.end));return '<g><title>'+esc(p.label+'：'+signed(p.value))+'</title><rect x="'+x+'" y="'+top+'" width="74" height="'+Math.max(1,Math.abs(y(p.start)-y(p.end)))+'" fill="'+(p.total?'#c9ba94':p.value<0?'#b39769':'#8ba99b')+'"/><text x="'+(x+37)+'" y="'+Math.max(16,top-10)+'" text-anchor="middle">'+signed(p.value)+'</text><text x="'+(x+37)+'" y="266" text-anchor="middle">'+esc(p.label)+'</text></g>'}).join('')+'</svg></div>';
  }
  const methods=`<details class="erp-methods"><summary>成熟业务分析方法：这个问题下一步怎么分析？</summary>
    <div class="erp-heat-scroll"><table><thead><tr><th>方法</th><th>适合回答</th><th>当前状态与边界</th></tr></thead><tbody>
    <tr><td>量价组合 / 利润桥</td><td>销量、结构、标价、折扣、单位成本各贡献多少？</td><td>已计算。层级中点法精确对账；交互项按中点分摊，属于会计分解。</td></tr>
    <tr><td>同比、环比、同季对比</td><td>下降是短期冲击、季节变化还是持续恶化？</td><td>已提供日/周/月/季/年。周同比留空，避免错配 ISO 周；观察两年不能确认稳定季节性。</td></tr>
    <tr><td>异常敏感性 / 稳健性检查</td><td>是否被少数特殊订单扭曲？</td><td>已提供原始与排除待核查订单口径，不修改源数据；排除口径不是修正后的事实。</td></tr>
    <tr><td>Pareto / ABC 与多层下钻</td><td>哪些商品、客户、渠道值得优先处理？</td><td>区域×品类已计算；进一步应按负向贡献排序，正向抵消单列，不把正负混合当普通占比。</td></tr>
    <tr><td>客户 Cohort / 复购留存</td><td>老客流失还是新客质量变差？</td><td>下一步：按首购月分组、去重订单定义复购，比较同龄客户毛利；当前报告未执行。</td></tr>
    <tr><td>本量利 / 盈亏平衡</td><td>卖多少才能覆盖成本？</td><td>需要固定费用和可变成本拆分；当前只有销售成本，不能冒算净利润或盈亏平衡点。</td></tr>
    <tr><td>预算差异 / 弹性预算</td><td>低于目标是业务量不够，还是单位经济性变差？</td><td>需要预算销量、预算价格与成本。实际同比不等于预算差异。</td></tr>
    <tr><td>时间序列分解与预测</td><td>趋势、季节性、一次性冲击各占什么角色？</td><td>先处理异常和不完整期间，再做回测，对比季节朴素基线并给预测区间；当前未自动预测。</td></tr>
    <tr><td>实验 / 准实验</td><td>折扣政策是否真的导致利润变化？</td><td>需实验组或可信对照、政策时间与假设检验；当前结果不支持直接宣称因果。</td></tr>
    </tbody></table></div><p class="erp-note">方法参考：<a href="https://otexts.com/fpp3/" target="_blank" rel="noopener">Forecasting: Principles and Practice</a> · <a href="https://itl.nist.gov/div898/handbook/eda/section3/eda35h.htm" target="_blank" rel="noopener">NIST 异常值处理</a>。未执行的方法明确列为下一步，不生成虚构结论。</p></details>`;
  window.ERPProfitReport={async render(host,data,{api}){
    const root=document.createElement('section');root.className='erp-profit-report';
    const before=host.querySelector('.erp-full-report');host.insertBefore(root,before||null);
    root.innerHTML='<header class="erp-report-head"><div><h2>利润为什么下降？</h2><p>把经营变化、比较基数与待核查订单拆开看。</p></div></header><div class="erp-profit-controls"><label>分析范围<select aria-label="利润分析范围"><option value="all">全部业务</option><option value="south">South</option><option value="westTech">West / Technology</option></select></label><p>年度分解：2024 → 2025 · 金额沿用源数据单位</p></div><div class="erp-profit-content" aria-live="polite"></div>'+methods;
    const content=root.querySelector('.erp-profit-content'),scopeControl=root.querySelector('select');
    let timeRows=[],currentScope='all',queries={};
    async function query(sql){const res=await api('/tools/sql',{method:'POST',body:{session_id:data.session_id,sql_query:sql,limit:800}});return res.data_preview||[];}
    function timeView(){
      const metric=content.querySelector('[data-metric]').value,labels={profit:'利润',sales:'销售额',quantity:'销售件数',margin:'利润率 %',net_unit_price:'成交均价',discount_pct:'加权折扣 %',unit_cost:'单位成本'};
      const chart=content.querySelector('[data-time-chart]');
      const vals=timeRows.flatMap(r=>[r[metric],...(metric==='profit'?[r.reviewed_profit]:[])]).filter(v=>v!=null).map(Number),lo=Math.min(0,...vals),hi=Math.max(1,...vals);
      const x=i=>55+i/Math.max(1,timeRows.length-1)*850,y=v=>225-(Number(v)-lo)/(hi-lo)*190;
      function path(key){let pen=false;return timeRows.map((r,i)=>{if(r[key]==null){pen=false;return ''}const p=(pen?'L':'M')+x(i)+','+y(r[key]);pen=true;return p}).join(' ')}
      chart.innerHTML='<p class="erp-note">旧金：'+labels[metric]+(metric==='profit'?' · 青灰虚线：排除待核查订单后的利润':' · 比率按期间汇总分子/分母重算，不平均日比率')+'</p><div class="erp-wide-chart"><svg viewBox="0 0 960 285" role="img" aria-label="'+labels[metric]+'时间趋势，数值可在期间选择器和明细表查看"><text x="8" y="35">'+n(hi)+'</text><text x="8" y="230">'+n(lo)+'</text><path d="'+path(metric)+'" fill="none" stroke="#cfba8b" stroke-width="2.5"/>'+(metric==='profit'?'<path d="'+path('reviewed_profit')+'" fill="none" stroke="#8ba99b" stroke-width="2" stroke-dasharray="6 5"/>':'')+timeRows.filter((_,i)=>i===0||i===timeRows.length-1||i%Math.ceil(timeRows.length/8)===0).map(r=>{const i=timeRows.indexOf(r);return '<text x="'+x(i)+'" y="263" text-anchor="middle">'+esc(r.period)+'</text>'}).join('')+'</svg></div>';
      const pick=content.querySelector('[data-period]');pick.innerHTML=timeRows.map((r,i)=>'<option value="'+i+'">'+esc(r.period)+'</option>').join('');pick.value=String(timeRows.length-1);periodView();
      content.querySelector('[data-time-table]').innerHTML='<table><thead><tr><th>期间起始</th><th>'+labels[metric]+'</th><th>利润环比变化</th><th>利润同比变化</th></tr></thead><tbody>'+timeRows.slice(-24).map(r=>'<tr><td>'+esc(r.period)+'</td><td>'+n(r[metric])+'</td><td>'+signed(r.previous_delta)+' / '+signed(r.previous_pct)+'%</td><td>'+signed(r.yoy_delta)+' / '+signed(r.yoy_pct)+'%</td></tr>').join('')+'</tbody></table><p class="erp-note">明细显示最近 '+Math.min(24,timeRows.length)+' / '+timeRows.length+' 个期间；图覆盖全部期间，期间选择器可查每一个点。百分比以比较期利润绝对值作分母；基期为零时不计算。</p>';
    }
    function periodView(){const r=timeRows[Number(content.querySelector('[data-period]').value)];content.querySelector('[data-period-detail]').textContent=r?`${r.period}：利润 ${n(r.profit)}；排除待核查订单 ${n(r.reviewed_profit)}；销量 ${n(r.quantity)}；订单 ${n(r.orders)}；利润率 ${n(r.margin)}%；加权折扣 ${n(r.discount_pct)}%；成交均价 ${n(r.net_unit_price)}；单位成本 ${n(r.unit_cost)}。利润同比变化 ${signed(r.yoy_delta)}，环比变化 ${signed(r.previous_delta)}。${r.has_records?'':'该期间无销售记录，金额填零不代表数据完整。'}`:'';}
    async function load(){
      scopeControl.disabled=true;content.innerHTML='<p role="status">正在对账销量、标价、折扣、成本与订单金额…</p>';
      try{
        currentScope=scopeControl.value;const q=window.ERPProfitQueries;
        queries={bridge:q.bridge(currentScope),orders:q.orders(currentScope),time:q.time('month',currentScope)};
        const bridges=await query(queries.bridge),orders=await query(queries.orders);timeRows=await query(queries.time);
        if(!root.isConnected)return;
        const reported=bridges.find(r=>r.scenario==='reported'),review=bridges.find(r=>r.scenario==='review');
        if(!reported)throw new Error('此范围没有可分析的数据');
        const reconciled=reported.comparable&&Math.abs(reported.reconciliation_error)<.01;
        const priority=factors.filter(([key])=>reported[key]<-.01).sort((a,b)=>reported[a[0]]-reported[b[0]]).slice(0,2);
        const nextSteps=priority.map(([key,label])=>label+'：'+why[key]).join(' ');
        content.innerHTML='<section class="erp-problem"><h3>先解释变化，再判断原因。</h3><p>销售件数 '+n(reported.base_quantity)+' → '+n(reported.current_quantity)+'；折扣贡献 '+signed(reported.discount_effect)+'；金额不一致项贡献 '+signed(reported.residual_effect)+'。</p><p class="erp-note">同品标价贡献 '+signed(reported.price_effect)+'，单位成本贡献 '+signed(reported.cost_effect)+'。'+(reconciled?'分解与利润差额对账通过（误差 < 0.01）。':'此范围不可比或未通过对账，暂不解释因素贡献。')+'</p><p><strong>优先核查：</strong>'+esc(nextSteps||'当前没有明显负向贡献，先核对口径与样本覆盖。')+'</p></section><section class="erp-report-chart"><h3>利润桥：每一个因素如何改变利润</h3>'+waterfall(reported)+'<p class="erp-note">旧金减少，青灰增加。中点法把交互项对称分摊；这是一种明确口径的会计分解，不是因果效应。选择因素可查看核查方向。</p><div class="erp-factor-list">'+factors.map(([key,label])=>'<button type="button" data-factor="'+key+'"><span>'+label+'</span><strong>'+signed(reported[key])+'</strong></button>').join('')+'</div><p class="erp-selection" data-factor-note>'+why.discount_effect+'</p></section><section class="erp-report-chart"><h3>异常基数，改变了多少判断？</h3><div class="erp-sensitivity"><div><span>原始口径 · 利润变化</span><strong>'+signed(reported.delta)+'</strong><b>'+signed(reported.change_pct)+'%</b></div><div><span>排除待核查订单 · 利润变化</span><strong>'+signed(review?.delta)+'</strong><b>'+signed(review?.change_pct)+'%</b></div></div><p>识别到 '+n(orders[0]?.total_flagged_orders||0)+' 笔待核查订单。规则：任一行的 |销售额 − 数量 × 标价 × (1−折扣)| > 0.01，敏感性分析排除整笔订单。</p><p class="erp-note">金额不一致贡献是公式残差变化，含舍入；排除订单对照还排除了订单中的正常业务，因此两者数值不同，不能相加。所有订单仍保留在源数据中。</p><div class="erp-heat-scroll"><table><thead><tr><th>订单 / 日期</th><th>区域</th><th>金额公式差额</th><th>整单利润</th></tr></thead><tbody>'+orders.map(r=>'<tr><td>'+esc(r.order_id)+'<small>'+esc(r.order_date)+'</small></td><td>'+esc(r.region)+'</td><td>'+signed(r.amount_gap)+'</td><td>'+n(r.profit)+'</td></tr>').join('')+'</tbody></table></div><p class="erp-note">订单明细展示整单金额（可包含当前分析范围以外的商品）；按金额差额绝对值排序，最多显示 20 笔。先查发票/订单原始金额，再查折扣审批和成本计价；不得直接将整单排除结果视为正确报表。</p></section><section class="erp-report-chart"><h3>换一个时间尺度，问题还成立吗？</h3><div class="erp-profit-controls"><label>时间粒度<select data-grain aria-label="时间粒度"><option value="day">日</option><option value="week">周（周一开始）</option><option value="month" selected>月</option><option value="quarter">季度</option><option value="year">年</option></select></label><label>观察指标<select data-metric aria-label="时间观察指标"><option value="profit">利润</option><option value="sales">销售额</option><option value="quantity">销售件数</option><option value="margin">利润率</option><option value="net_unit_price">成交均价</option><option value="discount_pct">加权折扣</option><option value="unit_cost">单位成本</option></select></label></div><p class="erp-note">日看突发订单，周看节奏，月看连续变化，季度降低短期噪声，年看整体。时间窗固定为 2024–2025；无记录金额填零不保证完整性，边界周可能不完整。周同比不计算，其他同比按上一年相同日/月/季/年匹配；闰日对比需谨慎。仅两年不能确认季节性。</p><div data-time-chart></div><label>查看期间<select data-period aria-label="查看期间"></select></label><p class="erp-selection" data-period-detail></p><details><summary>查看期间数据与同比 / 环比</summary><div class="erp-heat-scroll" data-time-table></div></details></section><details class="erp-methods"><summary>计算口径与 SQL 证据</summary><p>Π = Q × Σ[s × (p × (1−d) − c)] + R + E。Q 为件数、s 为 SKU 件数占比、p 为同品加权标价、d 为按标价金额加权折扣、c 为单位销售成本；R 为销售金额公式残差，E 为利润账差。</p><p>先拆 Q 与单位毛利，再拆商品组合 s 与同品毛利，最后拆价格、折扣、成本；各层用两期中点分摊。顺序已固定，不是所有因素排列的 Shapley。单期没有销售的商品使用另一期间单位指标；某一整期销量为零时不做因素分解。</p><pre data-evidence></pre></details>';
        timeView();
        content.querySelector('[data-evidence]').textContent=JSON.stringify({scope:currentScope,results:bridges,queries},null,2);
        content.querySelectorAll('[data-factor]').forEach(b=>b.addEventListener('click',()=>{content.querySelector('[data-factor-note]').textContent=why[b.dataset.factor];content.querySelectorAll('[data-factor]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)))}));
        content.querySelector('[data-metric]').addEventListener('change',timeView);content.querySelector('[data-period]').addEventListener('change',periodView);
        content.querySelector('[data-grain]').addEventListener('change',async e=>{
          const control=e.target;control.disabled=true;scopeControl.disabled=true;
          try{queries.time=q.time(control.value,currentScope);const rows=await query(queries.time);if(!root.isConnected)return;timeRows=rows;timeView();content.querySelector('[data-evidence]').textContent=JSON.stringify({scope:currentScope,results:bridges,queries},null,2);}
          catch(err){content.querySelector('[data-time-chart]').textContent='时间分析加载失败：'+err.message;content.querySelector('[data-time-table]').textContent='';content.querySelector('[data-period-detail]').textContent='';content.querySelector('[data-period]').innerHTML='';timeRows=[];}
          finally{control.disabled=false;scopeControl.disabled=false;}
        });
      }catch(err){content.textContent='利润深入分析暂未加载：'+err.message+'。上方原始报告仍可使用。';}
      finally{scopeControl.disabled=false;}
    }
    scopeControl.addEventListener('change',load);await load();
  }};
})();
